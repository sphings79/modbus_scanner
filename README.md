# 📡 Modbus TCP Scanner

> Python-Script zum systematischen Auslesen von Modbus-Registern über TCP —
> speziell für Geräte wie den **Marstek Venus D**, die bei nicht vorhandenen Registern
> die Verbindung trennen.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey)
![Protocol](https://img.shields.io/badge/Modbus-TCP-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

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

---

## 📖 Was ist das?

Viele Wechselrichter, Batteriespeicher und Energiemanager (z. B. Marstek, Huawei, SMA)
können über das **Modbus-Protokoll** ausgelesen werden. Modbus überträgt Messwerte und
Zustände als nummerierte *Register* — zum Beispiel: Register 34002 = Ladezustand in Prozent.

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

## ⚙️ Wie funktioniert es?

Das Script arbeitet Register für Register und geht dabei so vor:

```
1. TCP-Verbindung zum Gerät aufbauen (IP + Port)
2. Einzelnes Register per Modbus FC03 abfragen
3. Antwort prüfen:
   ├─ Wert erhalten  →  in CSV schreiben, anzeigen
   └─ Verbindung getrennt  →  Register in Sperrliste
4. Heartbeat-Register abfragen (nach dem Reconnect):
   ├─ Gerät antwortet  →  weiter mit nächstem Register
   └─ Keine Antwort    →  Cooldown verlängern, erneut versuchen
5. Alle N Register: kurze Pause (Gerät schonen)
6. Nächstes Register — gesperrte Register werden übersprungen
```

> **Warum Register einzeln?**
> Geräte wie der Marstek Venus D trennen die Verbindung sofort, wenn ein nicht vorhandenes
> Register angefragt wird. Durch Einzelabfragen mit Reconnect-Logik und Heartbeat-Prüfung
> schlägt sich das Script trotzdem durch den gesamten Bereich.

---

## 🖥️ Voraussetzungen

| Anforderung | Details |
|-------------|---------|
| **macOS** | 10.15 Catalina oder neuer (Intel oder Apple Silicon) |
| **Python** | 3.9 oder neuer (wird über Homebrew installiert) |
| **Netzwerk** | Mac und Gerät im gleichen Netzwerk, IP-Adresse und Port bekannt |

> ⚠️ **Marstek Venus D:** Verwendet Port `502`. Prüfe die Dokumentation deines Geräts für den korrekten Port.

---

## 📦 Installation

Die Installation ist **einmalig**. Danach kannst du das Script jederzeit starten.

### Schritt 1 — Homebrew installieren

Homebrew ist ein Paketmanager für macOS. Öffne die **Terminal**-App
(Programme → Dienstprogramme → Terminal) und füge ein:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Du wirst nach deinem macOS-Passwort gefragt. Falls Homebrew bereits installiert ist,
erhältst du eine entsprechende Meldung — das ist in Ordnung.

### Schritt 2 — Python installieren

```bash
brew install python

# Prüfen ob Python korrekt installiert ist:
python3 --version
# Python 3.14.0  (Versionsnummer kann abweichen)
```

### Schritt 3 — Virtual Environment anlegen

macOS erlaubt keine systemweite Installation von Python-Paketen. Wir legen daher eine
isolierte Umgebung an (ein „venv") — das ist der empfohlene Weg:

```bash
# Umgebung einmalig anlegen:
python3 -m venv ~/modbus-env

# Umgebung aktivieren (bei jedem neuen Terminal-Fenster wiederholen):
source ~/modbus-env/bin/activate

# Wenn aktiv, siehst du "(modbus-env)" am Anfang der Zeile:
# (modbus-env) %
```

### Schritt 4 — pymodbus installieren

```bash
# (venv muss aktiv sein!)
pip install pymodbus

# Erfolgreich wenn:
# Successfully installed pymodbus-3.13.0
```

> ✅ Die Installation ist abgeschlossen. Sie muss **nie wiederholt** werden —
> nur bei jedem neuen Terminal-Fenster das venv aktivieren:
> ```bash
> source ~/modbus-env/bin/activate
> ```

---

## 📄 Script speichern

Lade `modbus_scanner.py` aus dem [GitHub Repository](https://github.com/sphings79/modbus_scanner)
herunter und kopiere es in dein Home-Verzeichnis:

```bash
cp ~/Downloads/modbus_scanner.py ~/modbus_scanner.py

# Prüfen ob die Datei vorhanden ist:
ls ~/modbus_scanner.py
# /Users/deinname/modbus_scanner.py  ✓
```

---

## ▶️ Erster Start

Bei jedem Start: zuerst das venv aktivieren, dann das Script aufrufen.

```bash
# 1. venv aktivieren:
source ~/modbus-env/bin/activate

# 2. Script starten:
(modbus-env) % python ~/modbus_scanner.py --ip 192.168.1.123 --port 502 --start 30000 --count 500
```

> ⚠️ Ersetze `192.168.1.123` durch die tatsächliche IP-Adresse deines Geräts.
> Diese findest du im Router (Fritzbox, UniFi etc.) oder im Gerätedisplay.

---

## 🔧 Alle Parameter

### Grundeinstellungen

| Parameter | Pflicht | Standard | Beschreibung |
|-----------|:-------:|:--------:|--------------|
| `--ip` | ✅ | — | IP-Adresse des Modbus-Geräts |
| `--port` | — | `502` | TCP-Port des Geräts |
| `--unit` | — | `1` | Modbus Unit-ID (Slave-Adresse). Bei den meisten Geräten `1`. |
| `--start` | ✅ | — | Erstes Register (0-basiert), z. B. `30000` |
| `--count` | ✅ | — | Anzahl der Register, die gescannt werden sollen |
| `--delay` | — | `0.3` | Pause zwischen Registern in Sekunden |
| `--timeout` | — | `3.0` | TCP-Timeout in Sekunden |
| `--repeat` | — | aus | Kontinuierlich wiederholen bis `Strg+C` |
| `--interval` | — | `5.0` | Pause zwischen Wiederholungen (nur mit `--repeat`) |

### Ausgabe

| Parameter | Standard | Beschreibung |
|-----------|:--------:|--------------|
| `--verbose` / `-v` | aus | Fehler, Skips und Heartbeat-Bestätigung anzeigen |
| `--debug` | aus | Reconnects, Connect-Meldungen und pymodbus-Logs anzeigen (inkl. `-v`) |
| `--csv DATEI` | — | Treffer live als CSV speichern — wird bei Strg+C nicht unterbrochen |

### Schutz vor Gerät-Überlastung

| Parameter | Standard | Beschreibung |
|-----------|:--------:|--------------|
| `--heartbeat-reg REG` | — | Register das nach jedem Poll als Lebendprüfung abgefragt wird |
| `--pause-every N` | `50` | Alle N aktiven Register kurz pausieren (`0` = deaktiviert) |
| `--pause-duration SEC` | `3.0` | Dauer der periodischen Pause in Sekunden |
| `--max-retries N` | `5` | Maximale Reconnect-Versuche vor Cooldown |
| `--cooldown SEC` | `30.0` | Wartezeit nach zu vielen Fehlschlägen. Verdoppelt sich bei weiteren Fehlern. |

---

## 💡 Beispiele

### Marstek Venus D — typischer Scan

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 30000 \
    --count 500 \
    --heartbeat-reg 30100
```

### Mit CSV-Export und Heartbeat

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 30000 \
    --count 5000 \
    --heartbeat-reg 30100 \
    --delay 0.5 \
    --pause-every 30 \
    --pause-duration 5 \
    --csv ~/marstek_scan.csv
```

### Großen Bereich schonend scannen

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 0 \
    --count 10000 \
    --delay 0.5 \
    --pause-every 30 \
    --pause-duration 5 \
    --heartbeat-reg 30100 \
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
    --interval 10     # alle 10 Sekunden wiederholen

# Beenden mit Strg+C
```

### Erweiterte Ausgabe für Reverse Engineering

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 30000 \
    --count 500 \
    -v \
    --csv ~/scan_extended.csv
# -v zeigt nach dem Scan die erweiterte Interpretations-Tabelle
# CSV enthält: binary, ascii, uint32, int32, uint64
```

### Verbindungsprobleme debuggen

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 30000 \
    --count 100 \
    --debug
# zeigt alle Reconnects, Connect-Meldungen und pymodbus-Logs
```

---

## 📊 Ausgabe verstehen

### Terminal-Ausgabe

```
════════════════════════════════════════════════════════════════
  Modbus TCP Scanner
  Ziel       : 192.168.1.123:502  Unit 1
  Bereich    : Register 30000 … 30499 (500 Stk.)
  Heartbeat  : Reg 30100
  Pause      : alle 50 Reg. → 3.0s
  Ausgabe    : verbose
════════════════════════════════════════════════════════════════

     Reg   uint16    int16     hex  Status
  ──────────────────────────────────────────────────────
   30100     2300     2300   0x08fc  OK
   30101      120      120   0x0078  OK
   30200      115      115   0x0073  OK
  ──────────────────────────────────────────────────────
  ✔ OK: 3   ✘ Fehler: 12   ⏭ Übersprungen: 0
```

### Erweiterte Interpretations-Tabelle (mit `-v`)

```
  Erweiterte Interpretationen:
  Reg     bin                ascii    uint32        int32         uint64
  ──────────────────────────────────────────────────────────────────────
  33000  0000000000000000      ··           0             0             0
  33001  0000001000100011      ·#       8739          8739
  33002  0000000000001000      ··      524296        524296
```

### Bedeutung der Spalten

| Spalte | Bedeutung |
|--------|-----------|
| `uint16` | Vorzeichenloser 16-Bit-Wert (0–65535). Gut für Prozente, Spannung, Frequenz. |
| `int16` | Vorzeichenbehafteter 16-Bit-Wert (−32768–32767). Leistung, Strom — negativ = Einspeisung. |
| `hex` | Rohwert hexadezimal. Hilfreich beim Abgleich mit Dokumentation. |
| `binary` | 16-Bit Binärdarstellung. Hilft bei Bitmask-Registern einzelne Flags zu erkennen. |
| `ascii` | Die zwei Bytes als druckbare ASCII-Zeichen. Deutet auf `char`-Register hin (z. B. Gerätename). |
| `uint32` | Dieses + nächstes Register als vorzeichenloser 32-Bit-Wert. Typisch für Energiezähler. |
| `int32` | Dieses + nächstes Register als vorzeichenbehafteter 32-Bit-Wert. |
| `uint64` | Vier aufeinanderfolgende Register kombiniert. Typisch für Alarm-/Fault-Status. |

> 💡 **Skalierung beachten:** Viele Geräte senden z. B. Spannung × 10 — der Wert `2300`
> bedeutet dann 230,0 V. Die Skalierung steht in der Gerätedokumentation.

> 💡 **Ausgabe-Ebenen:**
> - **Standard** — nur Treffer + Heartbeat-Fehler + Cooldown-Meldungen
> - **`-v`** — zusätzlich Fehler, Skips, Heartbeat-OK, erweiterte Interpretations-Tabelle
> - **`--debug`** — alles inkl. Reconnects, Connect-Status, pymodbus-Logs

### CSV-Format

```csv
register,uint16,int16,hex,binary,ascii,uint32,int32,uint64
30100,2300,2300,0x08fc,0000100011111100,·8,150994944,150994944,
30101,120,120,0x0078,0000000001111000,·x,,, 
33000,0,0,0x0000,0000000000000000,··,8739,8739,
33001,8739,8739,0x2223,0010001000100011,·#,,,
```

> 💡 Die CSV wird **live nach jedem Treffer** geschrieben. Ein Abbruch mit `Strg+C`
> hinterlässt eine vollständige Datei mit allen bis dahin gescannten Registern.

---

## 🔴 Häufige Probleme

### Verbindung schlägt fehl

**Falscher Port:** Prüfe in der Gerätedokumentation welcher Port verwendet wird.

**Falsche IP:** Mac und Gerät müssen im selben Netzwerk sein. IP im Router nachschauen
(Fritzbox → Heimnetz → Netzwerk, oder UniFi → Clients).

**Firewall:** Manche Geräte erlauben nur Verbindungen aus bestimmten IP-Bereichen.

### Gerät hört nach einer Weile auf zu antworten

Das Gerät ist vermutlich überlastet. Empfohlene Einstellungen:

```bash
--delay 0.5 --pause-every 30 --pause-duration 5 --heartbeat-reg <bekanntes Register>
```

Der Heartbeat erkennt den Zustand automatisch und wartet mit exponentiell wachsendem
Cooldown bis das Gerät wieder antwortet.

### „command not found: python"

Immer `python3` verwenden oder zuerst das venv aktivieren:

```bash
source ~/modbus-env/bin/activate
# danach reicht: python
```

### Script nach Neustart nicht mehr gefunden

Checkliste für jeden neuen Terminal-Start:

```bash
# 1. venv aktivieren:
source ~/modbus-env/bin/activate

# 2. Prüfen ob pymodbus verfügbar ist:
python -c "import pymodbus; print('OK')"
# OK  ✓ Alles bereit
```

---

## Lizenz

MIT — frei verwendbar und anpassbar.
