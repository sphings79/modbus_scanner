# 📡 Modbus TCP Scanner

> Python-Script zum systematischen Auslesen von Modbus-Registern über TCP —
> speziell für Geräte wie den **Marstek Venus D**, die bei nicht vorhandenen Registern
> die Verbindung trennen.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey)
![Protocol](https://img.shields.io/badge/Modbus-TCP-green)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Version](https://img.shields.io/badge/Version-3.0.0-brightgreen)

---

## Inhaltsverzeichnis

- [Was ist das?](#-was-ist-das)
- [Wie funktioniert es?](#-wie-funktioniert-es)
- [Voraussetzungen](#-voraussetzungen)
- [Installation](#-installation)
- [Script speichern](#-script-speichern)
- [Erster Start](#-erster-start)
- [Alle Parameter](#-alle-parameter)
- [Beispiele](#-beispiele)
- [Ausgabe verstehen](#-ausgabe-verstehen)
- [Häufige Probleme](#-häufige-probleme)
- [Changelog](#-changelog)

---

## 📖 Was ist das?

Viele Wechselrichter, Batteriespeicher und Energiemanager (z. B. Marstek, Huawei, SMA)
können über das **Modbus-Protokoll** ausgelesen werden. Modbus überträgt Messwerte und
Zustände als nummerierte *Register* — zum Beispiel: Register 30000 = aktuelle Leistung.

Das Problem: Ohne offizielle Dokumentation weiß man oft nicht, welche Register existieren
und was sie bedeuten. Dieses Script scannt einen definierten Bereich Register für Register
und zeigt dir, welche Werte zurückgeliefert werden.

**Was es kann:**
- Register 0–65535 über TCP scannen
- Verbindungsabbrüche erkennen & automatisch wiederherstellen
- Problematische Register dauerhaft überspringen (Skip-Liste)
- Werte als `uint16`, `int16`, `HEX` und Binär anzeigen
- Erweiterte Typ-Interpretation: `uint32`, `int32`, `uint64`, ASCII — für Reverse Engineering
- Heartbeat-Register zur Lebendprüfung nach jedem Poll
- Exponentielles Backoff + Cooldown bei Gerät-Überlastung
- Periodische Pausen zum Schonen des Geräts
- Ergebnisse als CSV speichern (wird live geschrieben, überlebt Strg+C)
- Kontinuierlich wiederholen (`--repeat`)
- Drei Ausgabe-Ebenen: Standard / `-v` / `--debug`

**Was es nicht kann:**
- Register beschreiben (nur Lesen / FC03)
- Coil-Register lesen
- Automatisch deuten, was ein Wert bedeutet

---

## ✅ Marstek Venus D — getestet & optimiert

Dieser Scanner wurde ausgiebig mit dem **Marstek Venus D** getestet. Das Gerät trennt die
TCP-Verbindung bei jedem nicht vorhandenem Register — genau dafür ist der Scanner ausgelegt.

**Empfohlener Befehl für den Marstek Venus D:**

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 34000 \
    --count 6000 \
    --timeout 1 \
    --delay 0.1 \
    --pause-every 0 \
    -v
```

> `--timeout 1` und `--pause-every 0` beschleunigen den Scan erheblich.
> Der Scanner reconnectet nach jedem Verbindungsabbruch automatisch.

Bekannte Register-Bereiche mit Daten (Marstek Venus D):

| Bereich | Inhalt |
|---------|--------|
| 30000–30007 | Systemstatus, Spannung, Frequenz |
| 30020–30040 | Ladezustand, Leistung |
| 30100–30110 | Energiezähler |
| 30200–30214 | Temperaturen, weitere Zähler |
| 41000 | Heartbeat / Lebendprüfung (immer 0) |

---

## ⚙️ Wie funktioniert es?

Das Script arbeitet Register für Register und geht dabei so vor:

```
1. TCP-Verbindung zum Gerät aufbauen (IP + Port)
2. Einzelnes Register per Modbus FC03 abfragen
3. Antwort prüfen:
   ├─ Wert erhalten  →  in CSV schreiben, anzeigen
   └─ Verbindung getrennt  →  Register in Sperrliste, weiter
4. (Optional) Heartbeat-Register abfragen:
   ├─ Gerät antwortet  →  weiter mit nächstem Register
   └─ Keine Antwort    →  Cooldown verlängern, erneut versuchen
5. Alle N Register: kurze Pause (Gerät schonen, 0 = deaktiviert)
6. Nächstes Register — gesperrte Register werden übersprungen
7. Nach dem Scan: uint32/int32/uint64/ASCII berechnen, CSV aktualisieren
```

> **Warum Register einzeln?**
> Geräte wie der Marstek Venus D trennen die Verbindung sofort, wenn ein nicht vorhandenes
> Register angefragt wird. Durch Einzelabfragen mit Reconnect-Logik schlägt sich das Script
> trotzdem durch den gesamten Bereich.

---

## 🖥️ Voraussetzungen

| Anforderung | Details |
|-------------|---------|
| **macOS** | 10.15 Catalina oder neuer (Intel oder Apple Silicon) |
| **Python** | 3.9 oder neuer (wird über Homebrew installiert) |
| **Netzwerk** | Mac und Gerät im gleichen Netzwerk, IP-Adresse und Port bekannt |

> ⚠️ **Marstek Venus D:** Verwendet Port `502`.

---

## 📦 Installation

Die Installation ist **einmalig**. Danach kannst du das Script jederzeit starten.

### Schritt 1 — Homebrew installieren

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Schritt 2 — Python installieren

```bash
brew install python
python3 --version
# Python 3.14.0
```

### Schritt 3 — Virtual Environment anlegen

```bash
python3 -m venv ~/modbus-env
source ~/modbus-env/bin/activate
# (modbus-env) %
```

### Schritt 4 — pymodbus installieren

```bash
pip install pymodbus
# Successfully installed pymodbus-3.13.0
```

> ✅ Bei jedem neuen Terminal-Fenster: `source ~/modbus-env/bin/activate`

---

## 📄 Script speichern

Lade `modbus_scanner.py` aus dem [GitHub Repository](https://github.com/sphings79/modbus_scanner) herunter:

```bash
cp ~/Downloads/modbus_scanner.py ~/modbus_scanner.py
ls ~/modbus_scanner.py  # ✓
```

---

## ▶️ Erster Start

```bash
source ~/modbus-env/bin/activate
python ~/modbus_scanner.py --ip 192.168.1.123 --port 502 --start 30000 --count 500
```

---

## 🔧 Alle Parameter

### Grundeinstellungen

| Parameter | Pflicht | Standard | Beschreibung |
|-----------|:-------:|:--------:|--------------|
| `--ip` | ✅ | — | IP-Adresse des Modbus-Geräts |
| `--port` | — | `502` | TCP-Port des Geräts |
| `--unit` | — | `1` | Modbus Unit-ID |
| `--start` | ✅ | — | Erstes Register (0-basiert) |
| `--count` | ✅ | — | Anzahl der Register |
| `--delay` | — | `0.3` | Pause zwischen Registern in Sekunden |
| `--timeout` | — | `5.0` | TCP-Timeout in Sekunden |
| `--repeat` | — | aus | Kontinuierlich wiederholen bis `Strg+C` |
| `--interval` | — | `5.0` | Pause zwischen Wiederholungen (nur mit `--repeat`) |

### Ausgabe

| Parameter | Standard | Beschreibung |
|-----------|:--------:|--------------|
| `--verbose` / `-v` | aus | Fehler, Skips, Heartbeat-Bestätigung + erweiterte Interpretations-Tabelle |
| `--debug` | aus | Reconnects, Connect-Meldungen und pymodbus-Logs (inkl. `-v`) |
| `--csv DATEI` | — | Treffer live als CSV speichern |

### Schutz vor Gerät-Überlastung

| Parameter | Standard | Beschreibung |
|-----------|:--------:|--------------|
| `--heartbeat-reg REG` | — | Register das nach jedem Poll als Lebendprüfung abgefragt wird |
| `--pause-every N` | `50` | Alle N aktiven Register pausieren (`0` = deaktiviert) |
| `--pause-duration SEC` | `3.0` | Dauer der periodischen Pause in Sekunden |
| `--max-retries N` | `3` | Maximale Reconnect-Versuche vor Cooldown |
| `--cooldown SEC` | `10.0` | Wartezeit nach zu vielen Fehlschlägen |

---

## 💡 Beispiele

### Marstek Venus D — optimierter Schnellscan (empfohlen)

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 34000 \
    --count 6000 \
    --timeout 1 \
    --delay 0.1 \
    --pause-every 0 \
    -v
```

### Mit CSV-Export und Heartbeat

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 30000 \
    --count 5000 \
    --heartbeat-reg 41000 \
    --delay 0.5 \
    --pause-every 30 \
    --pause-duration 5 \
    --csv ~/marstek_scan.csv
```

### Großen Bereich scannen

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 0 \
    --count 10000 \
    --timeout 1 \
    --delay 0.1 \
    --pause-every 0 \
    --csv ~/scan_komplett.csv
```

### Kontinuierlich beobachten — z. B. beim Laden/Entladen

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 30000 \
    --count 500 \
    --repeat \
    --interval 10
```

### Verbindungsprobleme debuggen

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 30000 \
    --count 100 \
    --debug
```

---

## 📊 Ausgabe verstehen

```
     Reg   uint16    int16     hex  Status
  ──────────────────────────────────────────────────────
   30000      511      511  0x01ff  OK
   30001    65525      -11  0xfff5  OK
   30008        ✘        ✘       ✘  [ABBRUCH – ab nächstem Scan übersprungen]
   30020       99       99  0x0063  OK
  ──────────────────────────────────────────────────────
  ✔ OK: 3   ✘ Fehler: 1   ⏭ Übersprungen: 0
```

### Erweiterte Interpretations-Tabelle (mit `-v`)

```
  Erweiterte Interpretationen:
  Reg     bin                ascii    uint32        int32         uint64
  ──────────────────────────────────────────────────────────────────────
  30000  0000000111111111      ··       33488895       33488895             0
  30001  1111111111110101      ··
```

### Bedeutung der Spalten

| Spalte | Bedeutung |
|--------|-----------|
| `uint16` | Vorzeichenloser 16-Bit-Wert (0–65535). Prozente, Spannung, Frequenz. |
| `int16` | Vorzeichenbehafteter 16-Bit-Wert (−32768–32767). Leistung, Strom — negativ = Einspeisung. |
| `hex` | Rohwert hexadezimal. |
| `binary` | 16-Bit Binärdarstellung. Hilft bei Bitmask-Registern. |
| `ascii` | Die zwei Bytes als druckbare ASCII-Zeichen. Deutet auf Zeichenketten-Register hin. |
| `uint32` | Dieses + nächstes Register als vorzeichenloser 32-Bit-Wert. Typisch für Energiezähler. |
| `int32` | Dieses + nächstes Register als vorzeichenbehafteter 32-Bit-Wert. |
| `uint64` | Vier Register kombiniert. Typisch für Alarm-/Fault-Status. |

> 💡 **Skalierung beachten:** Viele Geräte senden z. B. Spannung × 10 — der Wert `2300`
> bedeutet dann 230,0 V.

> 💡 **Ausgabe-Ebenen:**
> - **Standard** — nur Treffer + Disconnect-Meldungen + Cooldown
> - **`-v`** — zusätzlich Fehler, Skips, Heartbeat-OK, erweiterte Interpretations-Tabelle
> - **`--debug`** — alles inkl. Reconnects, Connect-Status, pymodbus-Logs

### CSV-Format

```csv
register,uint16,int16,hex,binary,ascii,uint32,int32,uint64
30000,511,511,0x01ff,0000000111111111,··,33488895,33488895,
30020,99,99,0x0063,0000000001100011,·c,,,
```

---

## 🔴 Häufige Probleme

### Verbindung schlägt fehl

**Falscher Port:** Standard ist `502`. Im Router oder Gerätedisplay nachschauen.

**Falsche IP:** Mac und Gerät müssen im selben Netzwerk sein.

### Gerät hört nach einer Weile auf zu antworten

Das Gerät ist vermutlich überlastet. Empfohlene Einstellungen:

```bash
--delay 0.5 --pause-every 30 --pause-duration 5 --heartbeat-reg 41000
```

### Nur Fehler, keine Werte

Der gewählte Register-Bereich enthält keine Daten. Probiere andere Startregister oder
starte mit `-v` um zu sehen was passiert.

### „command not found: python"

Zuerst das venv aktivieren: `source ~/modbus-env/bin/activate`

### Script nach Neustart nicht mehr gefunden

```bash
source ~/modbus-env/bin/activate
python -c "import pymodbus; print('OK')"
```

---

## 📋 Changelog

### v3.0.0 — 2025-05-08

**Neue Features:**
- Erweiterte Register-Interpretation: `uint32`, `int32`, `uint64`, ASCII werden nach dem Scan
  automatisch berechnet und in die CSV geschrieben (bisher nur uint16/int16/hex)
- `-v` zeigt nach dem Scan eine vollständige Interpretations-Tabelle aller Treffer

**Verbesserte Standardwerte (Marstek Venus D optimiert):**
- `--timeout`: 3.0 s → **5.0 s**
- `--max-retries`: 5 → **3**
- `--cooldown`: 30.0 s → **10.0 s**

**Bugfixes:**
- Doppelter Reconnect nach Verbindungsabbruch eliminiert → deutlich schnellerer Scan
  (betrifft Scans ohne `--heartbeat-reg`)
- Disconnect-Events werden jetzt im Standard-Modus angezeigt (vorher nur mit `-v`)
- Verbindungsfehler in `connect()` werden jetzt mit `-v` angezeigt (vorher nur `--debug`)
- Reconnect-Kontext in `connect_with_backoff` jetzt mit `-v` sichtbar

### v2.0.0

- Erweiterte CSV-Ausgabe mit binary, ascii, uint32, int32, uint64
- Heartbeat-Mechanismus mit exponentiellem Cooldown
- Drei Ausgabe-Ebenen (Standard / -v / --debug)

---

## Lizenz

MIT — frei verwendbar und anpassbar.
