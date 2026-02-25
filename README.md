# Combined Media Player

Eine Home Assistant Custom Integration, die mehrere Media Player zu einem kombinierten Player zusammenführt – mit konfigurierbarer Prioritätslogik.

## Features

- **Mehrere Quellen** – beliebig viele `media_player`-Entitäten als Eingangsquellen
- **Prioritätsreihenfolge** – Position 1 = höchste Priorität, Position N = niedrigste
- **Intelligente Aktiverkennung** – spielende Quellen schlagen pausierte, pausierte schlagen eingeschaltete
- **Transparente Cover Art** – übernimmt das Bild der aktiven Quelle (funktioniert mit nativem Cover sowie mit [Media Cover Art](https://github.com/Levtos/test_art))
- **Vollständige Steuerung** – alle Befehle (Play, Pause, Volume, Next, ...) werden an die aktive Quelle weitergeleitet
- **Sauberes State-Modell** – nur `playing`, `idle`, `on`, `off` – kein `unavailable` oder `unknown`

## Prioritätslogik

| Tier | States | Beschreibung |
|------|--------|--------------|
| 1 | `playing`, `buffering` | Aktiv spielend |
| 2 | `paused`, `idle` | Pausiert / bereit |
| 3 | `on`, `standby` | Eingeschaltet, aber inaktiv |
| — | `off`, `unavailable`, `unknown` | Wird ignoriert |

Innerhalb desselben Tiers gewinnt die Quelle mit der niedrigeren Position (höhere Priorität).

**State-Mapping des kombinierten Players:**

| Aktive Quelle | Kombinierter Player |
|---------------|---------------------|
| `playing` / `buffering` | `playing` |
| `paused` / `idle` | `idle` |
| `on` / `standby` | `on` |
| Keine aktive Quelle | `off` |

## Installation

### HACS (empfohlen)

1. HACS öffnen → Integrationen → ⋮ → Benutzerdefinierte Repositories
2. URL: `https://github.com/Levtos/combined_mediaplayers`, Kategorie: Integration
3. „Combined Media Player" installieren und HA neu starten

### Manuell

Ordner `custom_components/combined_media_player` in dein `config/custom_components/`-Verzeichnis kopieren und HA neu starten.

## Konfiguration

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Combined Media Player**
2. Name vergeben (z. B. „Wohnzimmer")
3. Quell-Player auswählen – **die Reihenfolge der Auswahl bestimmt die Priorität**
4. Fertig – die Entität `media_player.<name>` erscheint sofort

Die Quellen und ihre Reihenfolge können jederzeit unter **Optionen** der Integration geändert werden.

## Beispiel: PS5 · AppleTV · HomePods

```
Prio 1: media_player.ps5             → Gaming   → eigene Thumbnails
Prio 2: media_player.appletv         → Streaming → eigene Cover
Prio 3: media_player.homepods_cover  → Musik     → iTunes-Cover via media_cover_art
```

Der kombinierte Player zeigt automatisch das Bild der gerade aktiven Quelle.
