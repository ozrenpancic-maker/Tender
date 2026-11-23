# KriptoMVP Android app

Minimalan Android Studio projekt (Kotlin): WebView koji učitava kripto-trading dashboard
(`../crypto-trading`) s tvog računala preko lokalne mreže. Nije prava "native" aplikacija s vlastitom
UI logikom - to je namjerno, da izbjegnemo dupliciranje cijelog dashboarda u dva jezika. Ono što ovo
daje, a PWA/"Dodaj na početni zaslon" ne može: pravi `.apk`, instalabilan i bez preglednika, bez
HTTPS/service-worker ograničenja (vidi `../crypto-trading/README.md`, odjeljak "Android").

## Preduvjeti

- **Android Studio** (besplatan, [developer.android.com/studio](https://developer.android.com/studio))
- Backend mora raditi na računalu, dostupan na lokalnoj mreži: u `crypto-trading/` pokreni
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port 8010
  ```
  i zapamti IP adresu računala (`ipconfig` na Windowsu, traži "IPv4 Address").

## Otvaranje i pokretanje

1. Otvori Android Studio → **Open** → odaberi mapu `android-app/` (ovu, ne cijeli repozitorij).
2. Pričekaj da Android Studio sinkronizira Gradle (prvi put preuzima ovisnosti - treba internet).
   Ako ponudi "Upgrade Gradle/AGP version", slobodno prihvati - verzije u projektu (AGP 8.5.2,
   Gradle 8.7) su bile aktualne u trenutku pisanja, mogu postojati novije.
3. Spoji Android telefon USB kabelom s uključenim USB debuggingom (Postavke → O telefonu → tapni
   "Broj izgradnje" 7 puta da otključaš Developer Options, pa Developer Options → USB debugging), ILI
   koristi Android emulator unutar Android Studija.
4. Klikni zeleni trokut **Run** (▶) u Android Studiju.
5. Pri prvom pokretanju app će tražiti adresu servera - unesi `<IP-adresa-računala>:8010` (npr.
   `192.168.1.50:8010`). Telefon i računalo moraju biti na istoj WiFi mreži.

Za gotov `.apk` za instalaciju bez USB kabela: **Build → Build App Bundle(s) / APK(s) → Build
APK(s)**, zatim prebaci `app/build/outputs/apk/debug/app-debug.apk` na telefon (npr. preko Google
Drivea, e-maila sebi, ili USB-a) i instaliraj ga izravno (telefon će tražiti dopuštenje "instaliraj
iz nepoznatih izvora" jer nije iz Play Storea - to je očekivano za vlastite/testne aplikacije).

## Struktura

- `app/src/main/java/.../MainActivity.kt` - cijela logika: WebView, postavke (dijalog za unos
  adrese servera, sprema se u SharedPreferences), swipe-to-refresh, progress bar, rukovanje
  greškama veze.
- `app/src/main/res/xml/network_security_config.xml` - dopušta obični HTTP (cleartext) promet,
  potrebno jer backend nema HTTPS. Pročitaj komentar u datoteci - namjerno je globalno dopušteno
  (ne vezano uz jednu IP adresu) jer se IP adresa računala mijenja (DHCP); može se pooštriti ako
  želiš.
- `app/src/main/res/mipmap-*/` - ikone aplikacije, generirane iz `crypto-trading/static/icons/`.

## Napomene

- Ovo NIJE uživo testirano (ni kompajlirano) - ovo razvojno okruženje nema Android SDK ni Android
  Studio. Sve XML datoteke su provjerene da su valjane (dobro formirane), a Kotlin kod je pažljivo
  pregledan, ali stvarni build/pokretanje treba napraviti u Android Studiju na tvom računalu. Ako
  naiđeš na grešku pri sinkronizaciji/buildu, najvjerojatnije je riječ o verziji AGP-a/Gradlea koja
  je u međuvremenu zastarjela - pusti Android Studio da je sam ažurira.
- Aplikacija radi samo dok je računalo s backendom upaljeno i na istoj WiFi mreži kao telefon - ovo
  nije "aplikacija u oblaku", nego udaljeni prikaz tvog lokalnog servera.
- Nema autentikacije - svatko na istoj WiFi mreži tko zna IP adresu i port može pristupiti
  dashboardu. U redu za kućnu/uredsku mrežu, ne za javnu.
