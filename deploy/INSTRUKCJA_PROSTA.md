# Instrukcja dla początkujących: aplikacja na własnym serwerze OVHcloud

Całość zajmuje około 1 godziny, z czego większość to czekanie. Nie musisz znać się na programowaniu.
Komendy **kopiujesz i wklejasz**: w oknie terminala wklejasz prawym przyciskiem myszy.

---

## KROK 1: Kup serwer VPS w OVHcloud

1. Wejdź na **ovhcloud.com/pl** → **Bare Metal & VPS** → **Serwery VPS**.
2. Wybierz **najtańszy plan** (np. *VPS-1*). Wystarczy na kilkadziesiąt ferm.
3. Podczas zamawiania:
   - **System operacyjny (obraz):** `Ubuntu 24.04`, bez żadnych dodatków.
   - **Lokalizacja:** najlepiej *Warszawa* (albo inna w Europie).
   - Okres: miesięczny.
4. Zapłać. Po kilku–kilkunastu minutach dostaniesz **e-mail od OVH** z:
   - **adresem IP** serwera (np. `51.68.123.45`),
   - **nazwą użytkownika** (zwykle `ubuntu`),
   - **hasłem** albo linkiem do hasła.

   Zachowaj ten e-mail.

## KROK 2: Kup domenę (adres strony)

1. W OVHcloud: **Domeny** → wpisz nazwę, np. `mojaferma-wentylacja.pl` → kup (domena .pl kosztuje kilkanaście zł na rok).
2. Poczekaj na e-mail, że domena jest aktywna.

## KROK 3: Połącz domenę z serwerem

1. Zaloguj się do **Panelu OVHcloud** (ovh.com/manager) → **Web Cloud** → **Domeny** → kliknij swoją domenę.
2. Zakładka **Strefa DNS** → przycisk **Dodaj rekord** → wybierz **A**.
3. Wypełnij:
   - **Subdomena:** zostaw puste (adres będzie `mojaferma-wentylacja.pl`) albo wpisz `app` (adres będzie `app.mojaferma-wentylacja.pl`).
   - **Cel:** adres IP serwera z e-maila (KROK 1).
4. Zapisz. Jeśli na liście był już inny rekord **A** dla tej samej subdomeny, **usuń go**.
5. Odczekaj **15–30 minut**.

## KROK 4: Wyślij aplikację na GitHub

GitHub to bezpłatny „magazyn” na kod, z którego serwer pobierze aplikację.

1. Załóż konto na **github.com** (Sign up).
2. W czacie Emergent kliknij **Save** → **Save to GitHub**, połącz konto i utwórz nowe repozytorium, np. `wentylacja`. Ustaw je jako **prywatne (Private)**.
   - Jeśli nie widzisz tej opcji, napisz do mnie w czacie, a sprawdzę to z pomocą techniczną.
3. Utwórz **klucz dostępu** (serwer użyje go zamiast hasła):
   - github.com → kliknij swoje zdjęcie (prawy górny róg) → **Settings** → na dole **Developer settings** → **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**.
   - Note: `serwer`, Expiration: `No expiration`, zaznacz tylko **repo** → **Generate token**.
   - **Skopiuj token** (zaczyna się od `ghp_…`) i zapisz go w notatniku. Drugi raz się nie wyświetli.

## KROK 5: Zaloguj się na serwer

**Windows:** kliknij Start → wpisz `PowerShell` → otwórz.
**Mac:** otwórz program **Terminal**.

Wpisz (zamień IP na swoje):
```
ssh ubuntu@51.68.123.45
```
- Na pytanie `Are you sure you want to continue connecting` wpisz `yes` i naciśnij Enter.
- Wpisz hasło z e-maila OVH. **Podczas wpisywania hasła nic się nie wyświetla**: to normalne, wpisz je i naciśnij Enter.
- Przy pierwszym logowaniu serwer może poprosić o zmianę hasła: podaj stare, potem dwa razy nowe.

## KROK 6: Zainstaluj aplikację (jedna komenda)

Wklej (zamień `TWOJ_LOGIN` na login z GitHuba, a `wentylacja` na nazwę repozytorium):
```
sudo git clone https://github.com/TWOJ_LOGIN/wentylacja.git /opt/wentylacja && sudo bash /opt/wentylacja/deploy/install.sh
```
- **Username:** Twój login GitHub.
- **Password:** wklej **token** `ghp_…` z KROKU 4 (nic się nie wyświetla, to normalne).

Skrypt zapyta o:
1. **domenę**, np. `mojaferma-wentylacja.pl`,
2. **Twój e-mail**, którym będziesz się logować,
3. **hasło** do aplikacji (dwa razy).

Resztę zrobi sam: zainstaluje programy, zabezpieczy serwer, uzyska certyfikat HTTPS, uruchomi broker MQTT i ustawi codzienną kopię bazy.
Na końcu zobaczysz zielony napis **GOTOWE!** z adresem strony.

## KROK 7: Pierwsze logowanie

1. Otwórz w przeglądarce `https://twoja-domena.pl` i zaloguj się e-mailem i hasłem z KROKU 6.
2. **Ustawienia → Klienci i sterowniki:** dodaj klienta (fermę), potem sterownik.
   Do pierwszych testów zaznacz przy sterowniku **„Symulator”**.
3. Przy sterowniku zobaczysz **login, hasło i tematy MQTT**. Przekaż je instalatorowi bramki sterownika Fatek.
   Bramka łączy się z: **Twoja domena, port 8883, TLS włączony**.
4. Na telefonie otwórz stronę i wybierz **„Dodaj do ekranu głównego”**. Aplikacja zainstaluje się jak zwykła aplikacja.

---

## Później

**Aktualizacja** (gdy coś zmienimy w Emergent): w czacie **Save to GitHub**, potem na serwerze:
```
sudo bash /opt/wentylacja/deploy/update.sh
```

**Powiadomienia e-mail/SMS:** na serwerze wpisz
```
sudo nano /opt/wentylacja/deploy/.env
```
i uzupełnij linie `SMTP_…` oraz `SMSAPI_…` (opis znajdziesz w `DEPLOY_VPS.md`, sekcja „Powiadomienia o alarmach”).
Zapisz: `Ctrl+O`, Enter, `Ctrl+X`. Potem wpisz:
```
cd /opt/wentylacja/deploy && sudo docker compose up -d backend
```

**Coś nie działa?** Skopiuj wynik tej komendy i wklej mi w czacie:
```
cd /opt/wentylacja/deploy && sudo docker compose ps && sudo docker compose logs --tail 50 backend web
```
