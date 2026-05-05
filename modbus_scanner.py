#!/usr/bin/env python3
"""
Modbus TCP Scanner
==================
Scannt Register-für-Register über TCP.
Erkennt Verbindungsabbrüche (z. B. Marstek bei nicht vorhandenen Registern)
und überspringt diese beim nächsten Durchlauf.

Ausgabe-Ebenen:
  Standard  : nur Treffer + Heartbeat-Fehler + Cooldown-Meldungen
  -v        : + Fehler, Skips, Heartbeat-Bestätigung
  --debug   : + Reconnects, Connect-Status, pymodbus-Logs

Schutzmechanismen:
  - Heartbeat nach jedem Register (--heartbeat-reg)
  - Exponentielles Backoff beim Reconnect
  - Periodische Pause alle N Register (--pause-every / --pause-duration)
  - Cooldown nach zu vielen Fehlschlägen (--max-retries / --cooldown)

Installation:
    pip install pymodbus

Verwendung:
    python modbus_scanner.py --ip 192.168.1.123 --port 502 \\
        --start 42000 --count 200 --heartbeat-reg 42000 [--csv ergebnis.csv]
"""

import argparse
import csv
import logging
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# pymodbus-Logs erst mal komplett aus — wird bei --debug wieder eingeschaltet
logging.getLogger("pymodbus").setLevel(logging.CRITICAL)

try:
    from pymodbus.client import ModbusTcpClient
    from pymodbus.exceptions import ModbusException, ConnectionException
except ImportError:
    print("❌  pymodbus nicht gefunden. Bitte installieren:")
    print("    pip install pymodbus")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Farben (ANSI)
# ──────────────────────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"
    BLUE   = "\033[94m"


# ──────────────────────────────────────────────────────────────────────────────
# Ausgabe-Ebenen
# ──────────────────────────────────────────────────────────────────────────────
LEVEL_DEFAULT = 0   # nur Treffer + kritische Meldungen
LEVEL_VERBOSE = 1   # + Fehler, Skips, Heartbeat-OK
LEVEL_DEBUG   = 2   # + Reconnects, Connect-Meldungen, pymodbus-Logs


# ──────────────────────────────────────────────────────────────────────────────
# Datenklasse
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class ScanResult:
    register:   int
    raw_uint16: Optional[int] = None
    raw_int16:  Optional[int] = None
    skip:       bool          = False
    error:      Optional[str] = None

    # Erweiterte Interpretationen (werden nach dem Scan befüllt)
    uint32:     Optional[int]  = None   # kombiniert mit nächstem Register
    int32:      Optional[int]  = None
    uint64:     Optional[int]  = None   # kombiniert mit 3 weiteren Registern
    ascii:      Optional[str]  = None   # druckbare ASCII-Zeichen aus den 2 Bytes
    binary:     Optional[str]  = None   # 16-Bit Binärdarstellung


def _to_uint32(hi: int, lo: int) -> int:
    """Zwei uint16 → uint32 (High-Word zuerst)."""
    return ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)

def _to_int32(hi: int, lo: int) -> int:
    v = _to_uint32(hi, lo)
    return v if v < 0x80000000 else v - 0x100000000

def _to_uint64(w0: int, w1: int, w2: int, w3: int) -> int:
    return ((w0 & 0xFFFF) << 48 | (w1 & 0xFFFF) << 32 |
            (w2 & 0xFFFF) << 16 | (w3 & 0xFFFF))

def _to_ascii(val: int) -> Optional[str]:
    """Gibt druckbare ASCII-Zeichen der 2 Bytes zurück, sonst None."""
    hi  = (val >> 8) & 0xFF
    lo  = val & 0xFF
    chars = ""
    for b in (hi, lo):
        chars += chr(b) if 0x20 <= b <= 0x7E else "·"
    return chars if any(0x20 <= (val >> s & 0xFF) <= 0x7E
                        for s in (8, 0)) else None

def annotate_results(results: list) -> list:
    """
    Befüllt die erweiterten Interpretationsfelder nach dem Scan.
    Geht über alle Ergebnisse und berechnet uint32/int32/uint64/ascii/binary.
    """
    reg_map = {r.register: r for r in results if r.raw_uint16 is not None}
    for r in results:
        if r.raw_uint16 is None:
            continue
        v = r.raw_uint16
        # Binär
        r.binary = f"{v:016b}"
        # ASCII
        r.ascii = _to_ascii(v)
        # uint32 / int32 mit nächstem Register
        nxt = reg_map.get(r.register + 1)
        if nxt is not None:
            r.uint32 = _to_uint32(v, nxt.raw_uint16)
            r.int32  = _to_int32(v, nxt.raw_uint16)
        # uint64 mit 3 weiteren Registern
        n1 = reg_map.get(r.register + 1)
        n2 = reg_map.get(r.register + 2)
        n3 = reg_map.get(r.register + 3)
        if n1 and n2 and n3:
            r.uint64 = _to_uint64(v, n1.raw_uint16, n2.raw_uint16, n3.raw_uint16)
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Scanner
# ──────────────────────────────────────────────────────────────────────────────
class ModbusScanner:
    def __init__(
        self,
        ip: str,
        port: int,
        unit_id: int,
        start: int,
        count: int,
        delay: float,
        timeout: float,
        pause_every: int,
        pause_duration: float,
        max_retries: int,
        cooldown: float,
        heartbeat_reg: Optional[int],
        csv_path: Optional[str],
        loglevel: int,
    ):
        self.ip             = ip
        self.port           = port
        self.unit_id        = unit_id
        self.start          = start
        self.count          = count
        self.delay          = delay
        self.timeout        = timeout
        self.pause_every    = pause_every
        self.pause_duration = pause_duration
        self.max_retries    = max_retries
        self.cooldown       = cooldown
        self.heartbeat_reg  = heartbeat_reg
        self.csv_path       = csv_path
        self.loglevel       = loglevel
        self.client: Optional[ModbusTcpClient] = None

        self.skip_set: set[int]      = set()
        self.results:  list[ScanResult] = []

    # ── Logging-Helfer ──────────────────────────────────────────────────────

    def _log(self, level: int, msg: str):
        """Gibt msg aus wenn loglevel >= level."""
        if self.loglevel >= level:
            print(msg)

    # ── Verbindung ──────────────────────────────────────────────────────────

    def _close(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    def connect(self, backoff: float = 0.0) -> bool:
        if backoff > 0:
            self._log(LEVEL_DEBUG, f"{C.YELLOW}  ⏳ Backoff {backoff:.0f}s …{C.RESET}")
            time.sleep(backoff)

        self._close()
        self.client = ModbusTcpClient(host=self.ip, port=self.port, timeout=self.timeout)
        try:
            ok = self.client.connect()
            if ok:
                self._log(LEVEL_DEBUG,
                    f"{C.GREEN}✔  Verbunden mit {self.ip}:{self.port}{C.RESET}")
            else:
                self._log(LEVEL_DEBUG,
                    f"{C.RED}✘  Verbindung fehlgeschlagen{C.RESET}")
            return ok
        except Exception as exc:
            self._log(LEVEL_DEBUG, f"{C.RED}✘  Verbindungsfehler: {exc}{C.RESET}")
            return False

    def connect_with_backoff(self, context: str = "") -> bool:
        backoff  = 1.0
        max_bo   = 30.0
        attempts = 0

        if context:
            self._log(LEVEL_DEBUG, f"{C.YELLOW}  ↻  {context}{C.RESET}")

        while True:
            ok = self.connect(backoff=backoff if attempts > 0 else 0)
            if ok:
                return True
            attempts += 1
            if attempts >= self.max_retries:
                print(
                    f"{C.RED}  ✘  {attempts}× Reconnect fehlgeschlagen — "
                    f"Cooldown {self.cooldown:.0f}s …{C.RESET}"
                )
                time.sleep(self.cooldown)
                attempts = 0
                backoff  = 1.0
            else:
                backoff = min(backoff * 2, max_bo)

    # ── Register lesen ───────────────────────────────────────────────────────

    def _read_one(self, reg: int) -> Optional[int]:
        if not self.client or not self.client.is_socket_open():
            return None
        try:
            rr = self.client.read_holding_registers(reg, count=1, device_id=self.unit_id)
            if rr is None or rr.isError():
                return None
            return rr.registers[0]
        except Exception:
            self._close()
            return None

    # ── Heartbeat ───────────────────────────────────────────────────────────

    def _do_heartbeat_read(self) -> bool:
        """Liest das Heartbeat-Register auf der aktuellen Verbindung.
        Gibt True zurück wenn Gerät antwortet, sonst False."""
        if self.heartbeat_reg is None:
            return True
        val = self._read_one(self.heartbeat_reg)
        if val is not None:
            self._log(LEVEL_VERBOSE,
                f"{C.GRAY}  ♥  Heartbeat Reg {self.heartbeat_reg} = {val}{C.RESET}")
            return True
        return False

    def heartbeat_or_recover(self) -> bool:
        """
        Korrekte Reihenfolge:

        1. Verbindung noch offen → Heartbeat direkt lesen.
           OK → weiter. Fehler → Verbindung schließen, weiter zu Schritt 2.

        2. Verbindung tot (durch fehlendes Register oder Heartbeat-Fehler):
           → Reconnect
           → Heartbeat NACH dem Reconnect
           → OK → Gerät lebt, war nur fehlendes Register → weiter
           → Fehler → Cooldown verlängern, erneut Reconnect + Heartbeat
                     → Cooldown verdoppeln bei jedem Fehlschlag (max. 5 min)
                     → Erst wenn Heartbeat OK, weiter mit nächstem Register
        """
        if self.heartbeat_reg is None:
            # Kein Heartbeat – nur reconnecten falls Verbindung weg
            if not self.client or not self.client.is_socket_open():
                self.connect_with_backoff(context="Reconnect nach Disconnect …")
            return True

        # Fall A: Verbindung noch offen → schneller Heartbeat-Check
        if self.client and self.client.is_socket_open():
            if self._do_heartbeat_read():
                return True
            # Heartbeat auf offener Verbindung fehlgeschlagen
            self._close()
            self._log(LEVEL_VERBOSE,
                f"{C.YELLOW}  ✘  Heartbeat fehlgeschlagen – Reconnect …{C.RESET}")

        # Fall B: Verbindung tot → Reconnect + Heartbeat-Verifikation
        # Cooldown startet bei base_cooldown und verdoppelt sich bei jedem Fehlschlag
        base_cooldown = max(2.0, self.cooldown / 8)
        current_cooldown = base_cooldown
        max_cooldown = 300.0
        attempt = 0

        while True:
            attempt += 1
            self._log(LEVEL_DEBUG,
                f"{C.YELLOW}  ↻  Reconnect Versuch {attempt} …{C.RESET}")

            ok = self.connect()
            if ok:
                # Heartbeat NACH dem Reconnect
                if self._do_heartbeat_read():
                    if attempt > 1:
                        self._log(LEVEL_VERBOSE,
                            f"{C.GREEN}  ✔  Gerät antwortet wieder (Versuch {attempt}){C.RESET}")
                    return True
                # Heartbeat schlug fehl → Gerät überlastet
                self._close()

            print(
                f"{C.RED}  ✘  Heartbeat Reg {self.heartbeat_reg} fehlgeschlagen "
                f"(Versuch {attempt}) — Cooldown {current_cooldown:.0f}s …{C.RESET}"
            )
            time.sleep(current_cooldown)
            current_cooldown = min(current_cooldown * 2, max_cooldown)

    # ── CSV ─────────────────────────────────────────────────────────────────

    def _csv_init(self):
        """Schreibt den CSV-Header falls Datei neu/leer ist."""
        if not self.csv_path:
            return
        path = Path(self.csv_path)
        if not path.exists() or path.stat().st_size == 0:
            with open(path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["register","uint16","int16","hex",
                                        "binary","ascii","uint32","int32","uint64"])

    def _csv_append(self, reg: int, uint16: int, int16: int):
        """Hängt eine einzelne Zeile sofort an die CSV an."""
        if not self.csv_path:
            return
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([reg, uint16, int16, f"{uint16:#06x}",
                                    f"{uint16:016b}", ""])

    def _csv_update_extended(self):
        """Schreibt die CSV neu mit allen erweiterten Feldern (nach annotate)."""
        if not self.csv_path:
            return
        path = Path(self.csv_path)
        rows = []
        try:
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
        except FileNotFoundError:
            return
        if not rows:
            return

        reg_map = {r.register: r for r in self.results if r.raw_uint16 is not None}

        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["register","uint16","int16","hex","binary",
                        "ascii","uint32","int32","uint64"])
            for row in rows[1:]:  # Header überspringen
                if not row:
                    continue
                try:
                    reg = int(row[0])
                except ValueError:
                    continue
                r = reg_map.get(reg)
                if r:
                    w.writerow([
                        r.register, r.raw_uint16, r.raw_int16,
                        f"{r.raw_uint16:#06x}", r.binary or "",
                        r.ascii or "",
                        r.uint32 if r.uint32 is not None else "",
                        r.int32  if r.int32  is not None else "",
                        r.uint64 if r.uint64 is not None else "",
                    ])

    # ── Scan-Durchlauf ──────────────────────────────────────────────────────

    def scan_once(self, run_number: int = 1) -> list[ScanResult]:
        self.results = []
        new_skips: set[int] = set()

        reg_list = list(range(self.start, self.start + self.count))
        total    = len(reg_list)

        print()
        print(f"{C.BOLD}{C.BLUE}╔═══════════════════════════════════════════════╗")
        print(f"║  Scan #{run_number:03d}  –  Register {self.start}–{self.start+self.count-1} ({total} Stk.)  ║")
        print(f"╚═══════════════════════════════════════════════╝{C.RESET}")
        print()
        print(f"  {'Reg':>6}  {'uint16':>7}  {'int16':>7}  {'hex':>6}  Status")
        print("  " + "─" * 54)

        self._csv_init()

        if not self.connect():
            if not self.connect_with_backoff(context="Erster Verbindungsaufbau …"):
                print(f"{C.RED}Abbruch: Kein Verbindungsaufbau möglich.{C.RESET}")
                return []

        reg_index = 0

        for reg in reg_list:

            # ── Übersprungen ──
            if reg in self.skip_set:
                result = ScanResult(register=reg, skip=True)
                self.results.append(result)
                self._log(LEVEL_VERBOSE,
                    f"  {reg:>6}  {'—':>7}  {'—':>7}  {'—':>6}  "
                    f"{C.GRAY}[übersprungen]{C.RESET}")
                time.sleep(self.delay * 0.1)
                continue

            # ── Periodische Pause ──
            if self.pause_every > 0 and reg_index > 0 and reg_index % self.pause_every == 0:
                print(f"{C.CYAN}  ⏸  Pause {self.pause_duration:.0f}s nach {self.pause_every} Registern …{C.RESET}")
                self._close()
                time.sleep(self.pause_duration)
                if not self.connect():
                    self.connect_with_backoff(context="Reconnect nach Pause …")

            reg_index += 1

            # ── Reconnect falls nötig ──
            if not self.client or not self.client.is_socket_open():
                self.connect_with_backoff(
                    context=f"Verbindung getrennt vor Register {reg} …")

            # ── Register lesen ──
            raw = self._read_one(reg)
            disconnected = (self.client is None)

            if raw is not None:
                int16  = raw if raw < 0x8000 else raw - 0x10000
                result = ScanResult(register=reg, raw_uint16=raw, raw_int16=int16)
                self.results.append(result)
                self._csv_append(reg, raw, int16)
                print(f"  {reg:>6}  {raw:>7}  {int16:>7}  {raw:#06x}  {C.GREEN}OK{C.RESET}")
            else:
                err = "Verbindung getrennt" if disconnected else "Keine Antwort"
                result = ScanResult(register=reg, error=err)
                self.results.append(result)
                if disconnected:
                    new_skips.add(reg)
                if disconnected:
                    marker = f"{C.RED}[ABBRUCH – ab nächstem Scan übersprungen]{C.RESET}"
                else:
                    marker = f"{C.YELLOW}[Fehler]{C.RESET}"
                self._log(LEVEL_VERBOSE,
                    f"  {reg:>6}  {'✘':>7}  {'✘':>7}  {'✘':>6}  {marker}")

            # ── Heartbeat ──
            if not self.heartbeat_or_recover():
                print(f"{C.RED}  Gerät dauerhaft nicht erreichbar. Scan abgebrochen.{C.RESET}")
                break

            time.sleep(self.delay)

        self._close()
        self.skip_set.update(new_skips)

        # ── Erweiterte Interpretationen berechnen ──
        annotate_results(self.results)
        if self.csv_path:
            self._csv_update_extended()

        ok_count   = sum(1 for r in self.results if r.raw_uint16 is not None)
        err_count  = sum(1 for r in self.results if r.error and not r.skip)
        skip_count = sum(1 for r in self.results if r.skip)
        new_skip_c = len(new_skips)

        print()
        print("  " + "─" * 54)
        print(f"  {C.GREEN}✔ OK: {ok_count}{C.RESET}   "
              f"{C.RED}✘ Fehler: {err_count}{C.RESET}   "
              f"{C.GRAY}⏭ Übersprungen: {skip_count}{C.RESET}   "
              f"{C.YELLOW}Neu markiert: {new_skip_c}{C.RESET}")
        if self.skip_set:
            sk = ", ".join(str(r) for r in sorted(self.skip_set))
            print(f"  {C.GRAY}Dauerhaft übersprungen: {sk}{C.RESET}")
        if self.csv_path and ok_count > 0:
            print(f"  {C.CYAN}💾 CSV: {self.csv_path} ({ok_count} Einträge, "
                  f"inkl. uint32/int32/uint64/ascii){C.RESET}")

        # ── Erweiterte Interpretations-Tabelle (verbose) ──
        hits = [r for r in self.results if r.raw_uint16 is not None]
        if hits and self.loglevel >= LEVEL_VERBOSE:
            print()
            print(f"  {C.BOLD}Erweiterte Interpretationen:{C.RESET}")
            print(f"  {'Reg':>6}  {'bin':>16}  {'ascii':>4}  "
                  f"{'uint32':>12}  {'int32':>12}  {'uint64':>20}")
            print("  " + "─" * 78)
            for r in hits:
                u32 = f"{r.uint32:>12}" if r.uint32 is not None else f"{'—':>12}"
                i32 = f"{r.int32:>12}"  if r.int32  is not None else f"{'—':>12}"
                u64 = f"{r.uint64:>20}" if r.uint64 is not None else f"{'—':>20}"
                asc = f"{r.ascii:>4}"   if r.ascii  else f"{'··':>4}"
                print(f"  {r.register:>6}  {r.binary:>16}  {asc}  {u32}  {i32}  {u64}")
        print()

        return self.results


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Modbus TCP Register-Scanner (Marstek-kompatibel)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--ip",      required=True,          help="IP-Adresse des Modbus-Geräts")
    p.add_argument("--port",    type=int, default=502,   help="TCP-Port (default: 502)")
    p.add_argument("--unit",    type=int, default=1,     help="Modbus Unit-ID (default: 1)")
    p.add_argument("--start",   type=int, required=True, help="Erstes Register (0-basiert)")
    p.add_argument("--count",   type=int, required=True, help="Anzahl Register")
    p.add_argument("--delay",   type=float, default=0.3,
                   help="Pause zwischen Registern in Sekunden (default: 0.3)")
    p.add_argument("--timeout", type=float, default=3.0,
                   help="TCP-Timeout in Sekunden (default: 3.0)")
    p.add_argument("--repeat",  action="store_true",
                   help="Kontinuierlich wiederholen (Strg+C zum Beenden)")
    p.add_argument("--interval", type=float, default=5.0,
                   help="Pause zwischen Wiederholungen in Sekunden (default: 5.0)")

    og = p.add_argument_group("Ausgabe")
    og.add_argument("--verbose", "-v", action="store_true",
                    help="Fehler, Skips und Heartbeat-Bestätigung anzeigen")
    og.add_argument("--debug",   action="store_true",
                    help="Reconnects, Connect-Meldungen und pymodbus-Logs anzeigen (inkl. -v)")
    og.add_argument("--csv", metavar="DATEI",
                    help="Treffer als CSV speichern (register,uint16,int16,hex)")

    sg = p.add_argument_group("Schutz vor Gerät-Überlastung")
    sg.add_argument("--heartbeat-reg", type=int, default=None, metavar="REG",
                    help="Register das nach jedem Poll als Lebendprüfung abgefragt wird")
    sg.add_argument("--pause-every", type=int, default=50, metavar="N",
                    help="Alle N aktiven Register kurz pausieren (default: 50, 0 = aus)")
    sg.add_argument("--pause-duration", type=float, default=3.0, metavar="SEC",
                    help="Dauer der periodischen Pause in Sekunden (default: 3.0)")
    sg.add_argument("--max-retries", type=int, default=5, metavar="N",
                    help="Max. Reconnect-Versuche vor Cooldown (default: 5)")
    sg.add_argument("--cooldown", type=float, default=30.0, metavar="SEC",
                    help="Wartezeit nach zu vielen Fehlschlägen (default: 30.0)")

    return p.parse_args()


def main():
    args = parse_args()

    # Ausgabe-Level bestimmen
    if args.debug:
        loglevel = LEVEL_DEBUG
        logging.getLogger("pymodbus").setLevel(logging.DEBUG)
    elif args.verbose:
        loglevel = LEVEL_VERBOSE
    else:
        loglevel = LEVEL_DEFAULT

    hb_label = f"Reg {args.heartbeat_reg}" if args.heartbeat_reg is not None else "deaktiviert"
    lvl_label = {LEVEL_DEFAULT: "Standard", LEVEL_VERBOSE: "verbose", LEVEL_DEBUG: "debug"}[loglevel]

    print()
    print(f"{C.BOLD}{'═'*60}")
    print(f"  Modbus TCP Scanner")
    print(f"  Ziel       : {args.ip}:{args.port}  Unit {args.unit}")
    print(f"  Bereich    : Register {args.start} … {args.start + args.count - 1} ({args.count} Stk.)")
    print(f"  Delay      : {args.delay}s  Timeout: {args.timeout}s")
    print(f"  Heartbeat  : {hb_label}")
    if args.pause_every:
        print(f"  Pause      : alle {args.pause_every} Reg. → {args.pause_duration}s")
    else:
        print(f"  Pause      : deaktiviert")
    print(f"  Backoff    : max. {args.max_retries} Versuche → Cooldown {args.cooldown}s")
    print(f"  Ausgabe    : {lvl_label}")
    if args.csv:
        print(f"  CSV        : {args.csv}")
    if args.repeat:
        print(f"  Modus      : Kontinuierlich (Intervall {args.interval}s)")
    else:
        print(f"  Modus      : Einmaliger Scan")
    print(f"{'═'*60}{C.RESET}")

    scanner = ModbusScanner(
        ip=args.ip,
        port=args.port,
        unit_id=args.unit,
        start=args.start,
        count=args.count,
        delay=args.delay,
        timeout=args.timeout,
        pause_every=args.pause_every,
        pause_duration=args.pause_duration,
        max_retries=args.max_retries,
        cooldown=args.cooldown,
        heartbeat_reg=args.heartbeat_reg,
        csv_path=args.csv,
        loglevel=loglevel,
    )

    run = 1
    try:
        while True:
            scanner.scan_once(run_number=run)
            if not args.repeat:
                break
            run += 1
            print(f"{C.GRAY}  Nächster Scan in {args.interval}s … (Strg+C zum Beenden){C.RESET}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}  Scan durch Benutzer abgebrochen.{C.RESET}\n")


if __name__ == "__main__":
    main()
