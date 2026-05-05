#!/usr/bin/env python3
"""
Modbus TCP Scanner
==================
Scannt Register-für-Register über TCP.
Erkennt Verbindungsabbrüche (z. B. Marstek bei nicht vorhandenen Registern)
und überspringt diese beim nächsten Durchlauf.

Installation:
    pip install pymodbus

Verwendung:
    python modbus_scanner.py --ip 192.168.1.100 --port 502 \
        --start 0 --count 100 [--unit 1] [--repeat] [--delay 0.2]
"""

import argparse
import socket
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

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
# Scanner-Kern
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class ScanResult:
    register:   int
    raw_uint16: Optional[int]  = None
    raw_int16:  Optional[int]  = None
    skip:       bool           = False   # dauerhaft überspringen
    error:      Optional[str]  = None


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
    ):
        self.ip      = ip
        self.port    = port
        self.unit_id = unit_id
        self.start   = start
        self.count   = count
        self.delay   = delay
        self.timeout = timeout
        self.client: Optional[ModbusTcpClient] = None

        # Register, die beim letzten Scan Abbrüche verursacht haben
        self.verbose  = False   # wird von außen gesetzt
        self.skip_set: set[int] = set()
        # Ergebnisse des aktuellen Durchlaufs
        self.results: list[ScanResult] = []

    # ── Verbindung ──────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Baut Verbindung (neu) auf. Gibt True zurück wenn erfolgreich."""
        self._close()
        self.client = ModbusTcpClient(
            host=self.ip,
            port=self.port,
            timeout=self.timeout,
        )
        try:
            ok = self.client.connect()
            if ok:
                if self.verbose:
                    print(f"{C.GREEN}✔  Verbunden mit {self.ip}:{self.port}{C.RESET}")
            else:
                print(f"{C.RED}✘  Verbindung fehlgeschlagen ({self.ip}:{self.port}){C.RESET}")
            return ok
        except Exception as exc:
            print(f"{C.RED}✘  Verbindungsfehler: {exc}{C.RESET}")
            return False

    def _close(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    # ── Ein einzelnes Register lesen ────────────────────────────────────────

    def _read_register(self, reg: int) -> ScanResult:
        result = ScanResult(register=reg)

        if not self.client or not self.client.is_socket_open():
            result.error = "nicht verbunden"
            return result

        try:
            rr = self.client.read_holding_registers(reg, count=1, device_id=self.unit_id)
        except ConnectionException as exc:
            result.error = f"Verbindung getrennt: {exc}"
            self._close()
            return result
        except ModbusException as exc:
            result.error = f"Modbus-Fehler: {exc}"
            return result
        except (OSError, socket.error) as exc:
            result.error = f"Socket-Fehler: {exc}"
            self._close()
            return result

        # Prüfen ob Antwort vorhanden (keine Daten → Gerät hat Verbindung getrennt)
        if rr is None or rr.isError():
            result.error = "Keine Antwort / Fehler-Response"
            # Wenn der Client-Socket danach tot ist, markieren wir Abbruch
            if not self.client or not self.client.is_socket_open():
                self._close()
            return result

        raw = rr.registers[0]
        result.raw_uint16 = raw
        # int16 signed interpretation
        result.raw_int16  = raw if raw < 0x8000 else raw - 0x10000
        return result

    # ── Scan-Durchlauf ──────────────────────────────────────────────────────

    def scan_once(self, run_number: int = 1) -> list[ScanResult]:
        """Führt einen vollständigen Scan durch und gibt Ergebnisse zurück."""
        self.results = []
        new_skips: set[int] = set()

        reg_list = list(range(self.start, self.start + self.count))
        total = len(reg_list)

        print()
        print(f"{C.BOLD}{C.BLUE}╔═══════════════════════════════════════════════╗")
        print(f"║  Scan #{run_number:03d}  –  Register {self.start}–{self.start+self.count-1} ({total} Stk.)  ║")
        print(f"╚═══════════════════════════════════════════════╝{C.RESET}")
        print()

        # Header
        print(
            f"  {'Reg':>6}  {'uint16':>7}  {'int16':>7}  {'hex':>6}  Status"
        )
        print("  " + "─" * 54)

        connected = self.connect()
        if not connected:
            print(f"{C.RED}Abbruch: Kein Verbindungsaufbau möglich.{C.RESET}")
            return []

        for reg in reg_list:
            # Übersprungene Register
            if reg in self.skip_set:
                result = ScanResult(register=reg, skip=True)
                self.results.append(result)
                if self.verbose:
                    print(
                        f"  {reg:>6}  {'—':>7}  {'—':>7}  {'—':>6}  "
                        f"{C.GRAY}[übersprungen]{C.RESET}"
                    )
                time.sleep(self.delay * 0.2)
                continue

            # War vorher keine Verbindung? Neu aufbauen.
            if not self.client or not self.client.is_socket_open():
                if self.verbose:
                    print(
                        f"{C.YELLOW}  ↻  Verbindung lost – Reconnect vor Register {reg}…{C.RESET}"
                    )
                connected = self.connect()
                if not connected:
                    print(f"{C.RED}  Reconnect fehlgeschlagen. Scan abgebrochen.{C.RESET}")
                    break

            result = self._read_register(reg)
            self.results.append(result)

            if result.raw_uint16 is not None:
                # Erfolg – immer anzeigen
                print(
                    f"  {reg:>6}  {result.raw_uint16:>7}  {result.raw_int16:>7}"
                    f"  {result.raw_uint16:#06x}  {C.GREEN}OK{C.RESET}"
                )
            else:
                # Fehler / Kein Datum – nur im verbose-Modus
                disconnected = (self.client is None)
                if disconnected:
                    new_skips.add(reg)
                if self.verbose:
                    marker = (
                        f"{C.RED}[ABBRUCH – übersprungen ab nächstem Scan]{C.RESET}"
                        if disconnected
                        else f"{C.YELLOW}[Fehler]{C.RESET}"
                    )
                    print(
                        f"  {reg:>6}  {'✘':>7}  {'✘':>7}  {'✘':>6}  "
                        f"{marker}  {C.GRAY}{result.error}{C.RESET}"
                    )

            time.sleep(self.delay)

        self._close()

        # Skip-Set für nächsten Lauf aktualisieren
        self.skip_set.update(new_skips)

        # Zusammenfassung
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
    p.add_argument("--ip",      required=True,        help="IP-Adresse des Modbus-Geräts")
    p.add_argument("--port",    type=int, default=502, help="TCP-Port (default: 502)")
    p.add_argument("--unit",    type=int, default=1,   help="Modbus Unit-ID (default: 1)")
    p.add_argument("--start",   type=int, required=True, help="Erstes Register (0-basiert)")
    p.add_argument("--count",   type=int, required=True, help="Anzahl Register")
    p.add_argument("--delay",   type=float, default=0.3,
                   help="Pause zwischen Registern in Sekunden (default: 0.3)")
    p.add_argument("--timeout", type=float, default=3.0,
                   help="TCP-Timeout in Sekunden (default: 3.0)")
    p.add_argument("--repeat",  action="store_true",
                   help="Kontinuierlich wiederholen (Strg+C zum Beenden)")
    p.add_argument("--interval",type=float, default=5.0,
                   help="Pause zwischen Wiederholungen in Sekunden (default: 5.0)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Fehler, Abbrüche und Reconnects anzeigen (default: nur Treffer)")
    return p.parse_args()


def main():
    args = parse_args()

    print()
    print(f"{C.BOLD}{'═'*56}")
    print(f"  Modbus TCP Scanner")
    print(f"  Ziel  : {args.ip}:{args.port}  Unit {args.unit}")
    print(f"  Bereich: Register {args.start} … {args.start + args.count - 1} ({args.count} Stk.)")
    print(f"  Delay : {args.delay}s  Timeout: {args.timeout}s")
    verbose_label = "verbose" if args.verbose else "nur Treffer"
    if args.repeat:
        print(f"  Modus : Kontinuierlich  (Intervall {args.interval}s)  [{verbose_label}]")
    else:
        print(f"  Modus : Einmaliger Scan  [{verbose_label}]")
    print(f"{'═'*56}{C.RESET}")

    scanner = ModbusScanner(
        ip=args.ip,
        port=args.port,
        unit_id=args.unit,
        start=args.start,
        count=args.count,
        delay=args.delay,
        timeout=args.timeout,
    )
    scanner.verbose = args.verbose

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