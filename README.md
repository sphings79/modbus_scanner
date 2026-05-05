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
Zustände als nummerierte *Register* — zum Beispiel: Register 42001 = Ladezustand in Prozent.

Das Problem: Ohne offizielle Dokumentation weiß man oft nicht, welche Register existieren
und was sie bedeuten. Dieses Script scannt einen definierten Bereich Register für Register
und zeigt dir, welche Werte zurückgeliefert werden.

**Was es kann:**
- Register 0–65535 über TCP scannen
- Verbindungsabbrüche erkennen & automatisch wiederherstellen
- Problematische Register dauerhaft überspringen (Skip-Liste)
- Werte als `uint16`, `int16` und `HEX` anzeigen
- Kontinuierlich wiederholen (`--repeat`)
- Wahlweise nur Treffer oder vollständige Ausgabe (`--verbose`)

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
   ├─ Wert erhalten  →  anzeigen, weiter zum nächsten Register
   └─ Kein Wert / Verbindung getrennt  →  Schritt 4
4. Reconnect durchführen, Register in Sperrliste aufnehmen
5. Nächstes Register — gesperrte Register werden übersprungen
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

> ⚠️ **Marstek Venus D:** Verwendet Port `502`, nicht den Standard-Modbus-Port `502`!

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

Lade `modbus_scanner.py` herunter und kopiere es in dein Home-Verzeichnis:

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
(modbus-env) % python ~/modbus_scanner.py --ip 192.168.1.100 --port 502 --start 42000 --count 200
```

> ⚠️ Ersetze `192.168.1.100` durch die tatsächliche IP-Adresse deines Geräts.
> Diese findest du im Router (Fritzbox, UniFi etc.) oder im Gerätedisplay.

---

## 🔧 Alle Parameter

| Parameter | Pflicht | Standard | Beschreibung |
|-----------|:-------:|:--------:|--------------|
| `--ip` | ✅ | — | IP-Adresse des Modbus-Geräts |
| `--port` | — | `502` | TCP-Port. Marstek: `502`, Standard: `502` |
| `--unit` | — | `1` | Modbus Unit-ID (Slave-Adresse). Bei den meisten Geräten `1`. |
| `--start` | ✅ | — | Erstes Register (0-basiert), z. B. `0` oder `42000` |
| `--count` | ✅ | — | Anzahl der Register, die gescannt werden sollen |
| `--delay` | — | `0.3` | Pause zwischen Registern in Sekunden. Erhöhen wenn das Gerät überfordert wirkt. |
| `--timeout` | — | `3.0` | TCP-Timeout in Sekunden. Erhöhen bei langsamen Verbindungen. |
| `--repeat` | — | aus | Kontinuierlich wiederholen bis `Strg+C` |
| `--interval` | — | `5.0` | Pause zwischen Wiederholungen (nur mit `--repeat`) |
| `--verbose` / `-v` | — | aus | Zeigt auch Fehler, Reconnects und übersprungene Register |

---

## 💡 Beispiele

### Marstek Venus D — typischer Scan

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 42000 \
    --count 200
```

### Großen Bereich scannen (Register 0–999)

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 0 \
    --count 1000 \
    --delay 0.5       # langsamer = schonender für das Gerät
```

### Kontinuierlich beobachten — z. B. beim Laden/Entladen

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 42000 \
    --count 200 \
    --repeat \
    --interval 10     # alle 10 Sekunden wiederholen

# Beenden mit Strg+C
```

### Ausführliche Ausgabe mit Fehlerdetails

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 42000 \
    --count 200 \
    --verbose
```

### Ausgabe in Datei speichern

```bash
python ~/modbus_scanner.py \
    --ip 192.168.1.123 \
    --port 502 \
    --start 42000 \
    --count 200 \
    | tee ~/modbus_ergebnis.txt

# Ausgabe erscheint im Terminal UND wird in die Datei gespeichert
```

---

## 📊 Ausgabe verstehen

Eine typische Ausgabe sieht so aus:

```
════════════════════════════════════════════════════════
  Modbus TCP Scanner
  Ziel  : 192.168.1.123:502  Unit 1
  Bereich: Register 42000 … 42199 (200 Stk.)
  Modus : Einmaliger Scan  [nur Treffer]
════════════════════════════════════════════════════════

╔═══════════════════════════════════════════════╗
║  Scan #001  –  Register 42000–42199 (200 Stk.)  ║
╚═══════════════════════════════════════════════╝

     Reg   uint16    int16     hex  Status
  ──────────────────────────────────────────────────────
   42000     1000     1000   0x03e8  OK
   42005      512      512   0x0200  OK
   42010    65000     -536   0xfde8  OK
   42020       48       48   0x0030  OK
  ──────────────────────────────────────────────────────
  ✔ OK: 4   ✘ Fehler: 12   ⏭ Übersprungen: 0
```

### Bedeutung der Spalten

| Spalte | Bedeutung |
|--------|-----------|
| `Reg` | Registernummer |
| `uint16` | Wert als vorzeichenlose Ganzzahl (0–65535). Gut für Prozente, Spannung, Frequenz. |
| `int16` | Wert als vorzeichenbehaftete Ganzzahl (−32768–32767). Wichtig für Leistung und Strom — negative Werte bedeuten oft Einspeisung. |
| `hex` | Rohwert hexadezimal. Hilfreich beim Abgleich mit Hersteller-Dokumentation. |

> 💡 **Skalierung beachten:** Viele Geräte senden z. B. Spannung in Einheiten von 0,1 V —
> der Wert `2300` bedeutet dann 230,0 V. Die Skalierung steht in der Gerätedokumentation.

---

## 🔴 Häufige Probleme

### Verbindung schlägt fehl

**Falscher Port:** Marstek Venus D verwendet `502`, nicht `502`. Prüfe die Gerätedokumentation.

**Falsche IP:** Mac und Gerät müssen im selben Netzwerk sein. IP im Router nachschauen
(Fritzbox → Heimnetz → Netzwerk, oder UniFi → Clients).

**Firewall:** Manche Geräte erlauben nur Verbindungen aus bestimmten IP-Bereichen.

### „command not found: python"

Immer `python3` verwenden oder zuerst das venv aktivieren:

```bash
source ~/modbus-env/bin/activate
# danach reicht: python
```

### Nur Fehler, keine Werte

Der gewählte Register-Bereich enthält möglicherweise keine Daten. Probiere andere
Startregister oder einen größeren Bereich. Mit `--verbose` siehst du die genauen Fehlermeldungen.

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
