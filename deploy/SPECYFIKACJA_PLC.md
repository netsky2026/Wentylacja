# Specyfikacja komunikacji MQTT – sterownik Fatek ↔ Marco Polo Wentylacja

## 1. Połączenie z brokerem

| Parametr | Wartość |
|---|---|
| Host | `marcopolo-wentylacja.pl` |
| Port | `8883` (MQTT over TLS, certyfikat Let's Encrypt, weryfikacja CA publicznego) |
| Wersja | MQTT 3.1.1 (lub 5) |
| Client ID | dowolny, unikalny, np. `fatek-<device_id>` |
| Login / hasło | osobne dla każdego sterownika – z panelu: Ustawienia → Sterowniki → ikona klucza |
| Keep-alive | 30–60 s |
| QoS | 1 |
| Retain | nie (false) |

Konto sterownika ma uprawnienia **tylko** do własnych tematów.

## 2. Tematy

| Kierunek | Temat |
|---|---|
| Sterownik → serwer (stan) | `<prefix>/<device_id>/state` |
| Serwer → sterownik (polecenia) | `<prefix>/<device_id>/command` |

`<prefix>` i `<device_id>` są widoczne w panelu przy danych sterownika (ikona klucza).

## 3. Stan – publikacja co **2–5 sekund** (JSON, UTF-8)

Brak wiadomości przez ponad 10 s = sterownik pokazany jako **offline**.

```json
{
  "model": "Fatek FBs-M",
  "chambers": [
    {
      "id": 0,
      "on": true,
      "heating": false,
      "mode": "auto",
      "temp": 21.5,
      "setpoint": 22.0,
      "humidity": 65.0,
      "co2": 1200,
      "curtain_left": 40,
      "curtain_right": 40,
      "chimney": 30,
      "water_lpm": 3.2,
      "water_total_l": 15432.0,
      "manual": {"curtain_left": 50, "curtain_right": 50, "chimney": 20}
    }
  ],
  "plant": {"power_kw": 4.1, "power_kwh": 12345.6, "water_lpm": 20.0, "water_total_l": 99999.0}
}
```

| Pole | Typ / jednostka | Wymagane | Opis |
|---|---|---|---|
| `chambers` | lista | TAK | dokładnie tyle elementów, ile komór ma sterownik; `id` = 0, 1, 2 … |
| `on` | bool | TAK | komora pracuje |
| `heating` | bool | TAK | grzanie załączone |
| `mode` | `"auto"` / `"manual"` | TAK | tryb pracy |
| `temp` | °C | TAK | temperatura |
| `setpoint` | °C | TAK | nastawa temperatury |
| `humidity` | % RH | TAK | wilgotność |
| `co2` | ppm | TAK | CO₂ |
| `curtain_left`, `curtain_right` | % **otwarcia** 0–100 | TAK | kurtyny (panel pokazuje % zamknięcia = 100 − wartość) |
| `chimney` | % otwarcia 0–100 | TAK | komin |
| `water_lpm` | l/min | nie | przepływ wody komory |
| `water_total_l` | litry, **licznik narastający** | nie* | licznik wody komory |
| `manual` | obiekt | nie | aktualne pozycje zadane w trybie ręcznym |
| `plant.power_kw` | kW | nie | moc chwilowa całej chlewni |
| `plant.power_kwh` | kWh, **licznik narastający** | nie* | licznik energii |
| `plant.water_lpm` / `plant.water_total_l` | l/min / litry narastająco | nie | woda całej chlewni |

\* Wymagane do zużycia dziennego, kosztów rzutów i raportów. Liczniki **nie mogą się zerować** (po restarcie sterownika muszą wrócić do ostatniej wartości – zapis w pamięci podtrzymywanej).

Liczby jako liczby JSON (nie tekst). Wiadomość z błędnym formatem lub złą liczbą komór jest **odrzucana**.

## 4. Polecenia – sterownik subskrybuje `<prefix>/<device_id>/command`

```json
{"type": "set_setpoint", "chamber": 0, "value": 22.5, "request_id": "a1b2..."}
{"type": "set_mode",     "chamber": 0, "value": "manual", "request_id": "..."}
{"type": "set_vent",     "chamber": 0, "value": {"curtain_left": 60, "curtain_right": 60, "chimney": 25}, "request_id": "..."}
```

| `type` | `value` | Działanie |
|---|---|---|
| `set_setpoint` | liczba 5–35 °C | nowa nastawa temperatury |
| `set_mode` | `"auto"` / `"manual"` | zmiana trybu |
| `set_vent` | obiekt z 1–3 polami, % **otwarcia** 0–100 | pozycje w trybie ręcznym (może przyjść tylko jedno pole) |

Po wykonaniu polecenia sterownik ma po prostu wysłać kolejny stan z nowymi wartościami (osobne potwierdzenie nie jest potrzebne).
Serwer codziennie o ustawionej godzinie (domyślnie 00:00) wysyła `set_mode: "auto"` do komór w trybie ręcznym.

## 5. Test

1. Podłącz się do brokera danymi sterownika i opublikuj przykładowy stan.
2. W panelu sterownik zmieni status na **online**, a wartości pojawią się w komorach.
3. Zmień nastawę w panelu → sterownik musi odebrać `set_setpoint` i odesłać nowy `setpoint` w stanie.
