# Instrukcja dla technika PLC – podłączenie sterownika Fatek (seria M) do systemu Marco Polo Wentylacja

Wersja: czerwiec 2026 · Panel: `https://marcopolo-wentylacja.pl`

System odbiera odczyty ze sterownika i wysyła do niego polecenia przez **MQTT z szyfrowaniem TLS**. Sterownik łączy się **wychodząco** do serwera – na fermie nie trzeba otwierać żadnych portów przychodzących ani publicznego IP.

---

## 1. Co technik dostaje od Marco Polo (osobno dla każdego sterownika)

Dane z panelu: Ustawienia → Sterowniki → ikona klucza (przycisk „Kopiuj”).

| Dane | Przykład |
|---|---|
| Broker (host) | `marcopolo-wentylacja.pl` |
| Port | `8883` (TLS) |
| Login MQTT | np. `kowalski-a` |
| Hasło MQTT | losowe, 20+ znaków |
| Temat stanu (publikuje sterownik) | `<prefix>/<device_id>/state` |
| Temat poleceń (subskrybuje sterownik) | `<prefix>/<device_id>/command` |
| Liczba komór | np. 6 (komory numerowane od 0) |

Konto ma dostęp **wyłącznie** do swoich dwóch tematów. Hasła nie wysyłać otwartym tekstem w e-mailach grupowych.

## 2. Wymagania po stronie sterownika

- Fatek seria M z firmware obsługującym **klienta MQTT z TLS** (UperLogic). Jeśli firmware nie obsługuje TLS – aktualizacja firmware albo bramka MQTT.
- Stały dostęp do internetu (router / LTE), ruch **wychodzący TCP 8883** niezablokowany.
- Poprawny czas w sterowniku (NTP) – wymagany do weryfikacji certyfikatu TLS.
- Certyfikat serwera: publiczny **Let's Encrypt** (odnawiany automatycznie). Sterownik ma ufać publicznym CA; jeśli wymaga wgrania CA – użyć głównego certyfikatu **ISRG Root X1**.

## 3. Ustawienia klienta MQTT

| Parametr | Wartość |
|---|---|
| Wersja | MQTT 3.1.1 (lub 5) |
| Client ID | unikalny, np. `fatek-<device_id>` |
| Keep-alive | 30–60 s |
| Clean session | tak |
| QoS publikacji i subskrypcji | 1 |
| Retain | nie |
| Ponowne łączenie | automatyczne, co 5–30 s po utracie połączenia |

## 4. Wysyłanie stanu – co **2–5 sekund**

Temat: `<prefix>/<device_id>/state` · format: **JSON, UTF-8** · liczby jako liczby (nie tekst).

```json
{
  "model": "Fatek M",
  "ack": "5075339505334838",
  "chambers": [
    {
      "id": 0, "on": true, "heating": false, "mode": "auto",
      "temp": 21.5, "setpoint": 22.0, "humidity": 65.0, "co2": 1200,
      "curtain_left": 40, "curtain_right": 40, "chimney": 30,
      "water_lpm": 3.2, "water_total_l": 15432.0,
      "manual": {"curtain_left": 50, "curtain_right": 50, "chimney": 20}
    }
  ],
  "plant": {"power_kw": 4.1, "power_kwh": 12345.6, "water_lpm": 20.0, "water_total_l": 99999.0}
}
```

Lista `chambers` musi zawierać **dokładnie tyle komór, ile ma sterownik** (`id` = 0, 1, 2 …). Inaczej wiadomość jest odrzucana.

| Pole | Jednostka | Wymagane | Opis |
|---|---|---|---|
| `id` | liczba | TAK | numer komory od 0 |
| `on` | true/false | TAK | komora pracuje |
| `heating` | true/false | TAK | grzanie załączone |
| `mode` | `"auto"` / `"manual"` | TAK | tryb pracy |
| `temp` | °C | TAK | temperatura |
| `setpoint` | °C | TAK | nastawa |
| `humidity` | % RH | TAK | wilgotność |
| `co2` | ppm | TAK | CO₂ |
| `curtain_left`, `curtain_right` | % **otwarcia** 0–100 | TAK | kurtyny (panel pokazuje % zamknięcia = 100 − wartość) |
| `chimney` | % otwarcia 0–100 | TAK | komin |
| `water_lpm` | l/min | nie | przepływ wody komory |
| `water_total_l` | litry, **licznik narastający** | zalecane | woda komory – do zużycia i kosztów rzutów |
| `manual` | obiekt | nie | pozycje zadane w trybie ręcznym |
| `plant.power_kw` | kW | nie | moc chwilowa chlewni |
| `plant.power_kwh` | kWh, **licznik narastający** | zalecane | energia chlewni – do raportów i kosztów |
| `plant.water_lpm`, `plant.water_total_l` | l/min, litry narastająco | nie | woda całej chlewni |
| `ack` | tekst | do testu | `request_id` ostatnio odebranego polecenia `ping` |

**Liczniki narastające nie mogą się zerować** – po zaniku zasilania sterownik musi kontynuować od ostatniej wartości (pamięć podtrzymywana / retain). Brak danych przez 10 s = sterownik **offline** w panelu (wpis w dzienniku po 30 s); po ustawionym czasie (domyślnie 5 min) klient dostaje alarm.

## 5. Odbieranie poleceń

Sterownik subskrybuje `<prefix>/<device_id>/command`. Po wykonaniu polecenia wystarczy wysłać kolejny stan z nowymi wartościami (osobne potwierdzenie niepotrzebne – poza `ping`).

```json
{"type": "set_setpoint", "chamber": 0, "value": 22.5, "request_id": "a1b2c3"}
{"type": "set_mode",     "chamber": 0, "value": "manual", "request_id": "a1b2c4"}
{"type": "set_vent",     "chamber": 0, "value": {"curtain_left": 60, "chimney": 25}, "request_id": "a1b2c5"}
{"type": "ping", "request_id": "5075339505334838"}
```

| `type` | `value` | Co ma zrobić sterownik |
|---|---|---|
| `set_setpoint` | liczba 5–35 (°C) | ustawić nową nastawę temperatury komory |
| `set_mode` | `"auto"` / `"manual"` | przełączyć tryb komory |
| `set_vent` | obiekt z 1–3 polami: `curtain_left`, `curtain_right`, `chimney` – % **otwarcia** 0–100 | ustawić pozycje w trybie ręcznym (może przyjść tylko jedno pole) |
| `ping` | – (bez `chamber`) | wpisać `request_id` do pola `"ack"` i **od razu** wysłać stan |

Uwagi:
- Codziennie o ustawionej godzinie (domyślnie 00:00) serwer wysyła `set_mode: "auto"` do komór w trybie ręcznym.
- Nieznane `type` lub złe wartości – zignorować.
- Zabezpieczenia technologiczne (minimalne otwarcie, blokady przy wysokiej temperaturze) pozostają **w sterowniku** – polecenia z panelu nie mogą ich obchodzić.
- Bez internetu sterownik pracuje samodzielnie w AUTO.

## 6. Uruchomienie i test – krok po kroku (razem z Marco Polo)

1. Marco Polo dodaje sterownik w panelu (liczba komór) i przekazuje dane z punktu 1.
2. Technik wpisuje dane MQTT w sterowniku i uruchamia publikację stanu.
3. W panelu: **Ustawienia → Sterowniki → ikona aktywności („Podgląd MQTT”)**. Podgląd odświeża się co 2 s i pokazuje:
   - **Broker: połączony / Sterownik: online**,
   - ostatnią wiadomość od sterownika (treść JSON) i wynik: **„Przyjęta – format poprawny”** albo **„Odrzucona: <powód>”**.
4. Kliknąć **„Wyślij test”** → musi pojawić się **„Sterownik potwierdził odbiór po X s”** (sterownik odesłał `ack`).
5. Zmienić nastawę jednej komory w panelu → w podglądzie widać wysłane polecenie, a w kolejnym stanie nowy `setpoint`.
6. Sprawdzić tryb ręczny: przełączyć komorę na RĘCZNY, przesunąć kurtynę/komin, sprawdzić fizyczny ruch.
7. Sprawdzić liczniki: po kilku minutach w zakładce „Dane” rośnie zużycie wody i prądu.
8. Odłączyć internet na ~1 min i podłączyć – sterownik ma sam wrócić (w dzienniku: „sterownik znów online”).

## 7. Najczęstsze problemy

| Objaw w Podglądzie MQTT | Przyczyna / co zrobić |
|---|---|
| „Jeszcze nic nie przyszło” | brak połączenia: zły host/port/login/hasło, zablokowany port 8883, brak TLS, zły czas w sterowniku (TLS), zły temat |
| „To nie jest poprawny JSON” | błąd składni – cudzysłowy, przecinki, kodowanie inne niż UTF-8 |
| „Zła liczba komór: przysłano X, sterownik ma Y” | lista `chambers` musi mieć Y elementów – lub Marco Polo zmienia liczbę komór w panelu |
| „Pola id komór muszą być liczbami 0–N” | numeracja komór od 0, bez przerw |
| „Komora id=…: brak lub nieprawidłowa wartość pól: …” | brak pola albo wartość jako tekst (`"21.5"` zamiast `21.5`) |
| „Brak potwierdzenia po 15 s” po „Wyślij test” | sterownik nie subskrybuje tematu `command` albo nie odsyła `ack` |
| Sterownik co chwilę offline | publikacja rzadziej niż co 10 s albo niestabilny internet |

## 8. Kontakt

Marco Polo Wentylacja – dane kontaktowe na stronie `https://marcopolo-wentylacja.pl`.
