"""Turkish Text Style and Identity Neutralizer (Türkçe Yazı Stili ve Kimlik Nötrleyici).

Anonymizes, cleans, and standardizes Turkish chat messages to strip stylometric
markers, colloquialisms, slang, profanity, and idiosyncratic writing patterns.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Turkish Case Translation Tables & Helpers
# ---------------------------------------------------------------------------
TR_LOWER_MAP = str.maketrans({
    "I": "ı",
    "İ": "i",
})

TR_UPPER_MAP = str.maketrans({
    "ı": "I",
    "i": "İ",
})


def tr_lower(text: str) -> str:
    """Turkish-aware lowercase conversion."""
    if not text:
        return text
    return text.translate(TR_LOWER_MAP).lower()


def tr_upper(text: str) -> str:
    """Turkish-aware uppercase conversion."""
    if not text:
        return text
    return text.translate(TR_UPPER_MAP).upper()


def tr_capitalize(text: str) -> str:
    """Turkish-aware capitalization (first letter uppercase, rest lowercase)."""
    if not text:
        return text
    return tr_upper(text[0]) + tr_lower(text[1:])


def is_irregular_casing(word: str) -> bool:
    """Check if a word has alternating or random casing (e.g. 'bÖyLe', 'yAzI')."""
    if len(word) < 2:
        return False
    # If not all letters, only check alpha portion
    alphas = [c for c in word if c.isalpha()]
    if len(alphas) < 2:
        return False
    has_upper = any(c.isupper() for c in alphas)
    has_lower = any(c.islower() for c in alphas)
    # Irregular if it has both upper and lower, and uppercase appears after index 0
    return has_upper and has_lower and any(c.isupper() for c in alphas[1:])


# ---------------------------------------------------------------------------
# Legitimate Turkish Double-Letter Words (to prevent over-collapsing)
# ---------------------------------------------------------------------------
DOUBLE_LETTER_WORDS: Set[str] = {
    "saat", "saati", "saate", "saatte", "saatten", "saatler",
    "cemaat", "kanaat", "maalesef", "millet", "milleti", "millette", "milletler",
    "kuvvet", "kuvveti", "kuvvetle", "kuvvetli",
    "dikkat", "dikkati", "dikkatle", "dikkatli", "dikkatsiz",
    "hissiyat", "iddia", "iddiası", "fiil", "fiili", "fiiller",
    "şiir", "şiiri", "şiirler", "kooperatif", "bakkal", "tavassut",
    "maddeler", "madde", "maddesi", "hissi", "affet", "affetti", "affeder",
    "reddet", "reddedildi", "reddetmek", "zannet", "zannedersem",
    "elli", "şiddet", "şiddetli", "hürriyet", "cumhuriyet", "medeniyet",
    "muhakkak", "halloldu", "hallolur", "hassas", "hassa", "teessüf",
    "teessür", "tebessüm", "tecessüs", "tahammül", "tahayyül", "tecelliyat",
    "mücellit", "müeccel", "mürekkep", "mürettip", "mürettebat", "mükemmel",
    "müessese", "müessir", "mümtaz", "rezzak", "cellat", "fellah", "seccade",
    "ferrari", "piazza", "pizza", "pizzalar", "espresso", "latte", "cappuccino",
}

# Common elongated roots and their normalized forms
ELONGATED_STEM_MAP: Dict[str, str] = {
    "lütfeeeen": "lütfen",
    "lütfeen": "lütfen",
    "lutfen": "lütfen",
    "nolurrrr": "ne olur",
    "nolurrr": "ne olur",
    "nolurr": "ne olur",
    "nolur": "ne olur",
    "yhaaa": "ya",
    "yhaa": "ya",
    "yha": "ya",
    "yaaa": "ya",
    "yaa": "ya",
    "offff": "of",
    "offf": "of",
    "off": "of",
    "çoook": "çok",
    "çook": "çok",
    "evveeeet": "evet",
    "evvet": "evet",
    "hayıııır": "hayır",
    "hayıır": "hayır",
    "güzeeeel": "güzel",
    "güzeel": "güzel",
    "tamammmm": "tamam",
    "tamamm": "tamam",
    "pekkkki": "peki",
    "pekii": "peki",
    "selaaam": "selam",
    "selamm": "selam",
    "merhabaaa": "merhaba",
    "süpeeeer": "süper",
    "harikaaa": "harika",
}

# ---------------------------------------------------------------------------
# Slang, Contractions, Colloquialisms & Shorthands
# ---------------------------------------------------------------------------
SLANG_AND_SHORTHAND_MAP: Dict[str, str] = {
    # Greetings, farewells, acknowledgments
    "slm": "selam",
    "mrb": "merhaba",
    "merb": "merhaba",
    "nbr": "ne haber",
    "naber": "ne haber",
    "naptın": "ne yaptın",
    "naptin": "ne yaptın",
    "naptınız": "ne yaptınız",
    "naptiniz": "ne yaptınız",
    "eyw": "teşekkür ederim",
    "eyv": "teşekkür ederim",
    "eyvallah": "teşekkür ederim",
    "tşk": "teşekkürler",
    "tsk": "teşekkürler",
    "tşkler": "teşekkürler",
    "tskler": "teşekkürler",
    "thx": "teşekkürler",
    "tmm": "tamam",
    "tm": "tamam",
    "tmam": "tamam",
    "ok": "tamam",
    "okay": "tamam",
    "okey": "tamam",
    "oke": "tamam",
    "hg": "hoş geldin",
    "hb": "hoş bulduk",
    "bb": "hoşça kal",
    "bye": "hoşça kal",
    "bay bay": "hoşça kal",
    "kib": "kendine iyi bak",
    "grs": "görüşürüz",
    "grş": "görüşürüz",
    "görs": "görüşürüz",
    "gorusuruz": "görüşürüz",
    "hll": "helal",
    "rca": "rica ederim",
    "rck": "rica ederim",
    "sa": "selamünaleyküm",
    "s.a": "selamünaleyküm",
    "s.a.": "selamünaleyküm" if False else "selamünaleyküm",
    "as": "aleyküm selam",
    "a.s": "aleyküm selam",
    "a.s.": "aleyküm selam",
    "gnydn": "günaydın",
    "gnaydın": "günaydın",
    "gnaydin": "günaydın",
    "ig": "iyi geceler" if False else "iyi geceler",
    "iigeceler": "iyi geceler",
    "iyigeceler": "iyi geceler",

    # Common texting words & particles
    "hyr": "hayır",
    "ewt": "evet",
    "evt": "evet",
    "ztn": "zaten",
    "noldu": "ne oldu",
    "nolduu": "ne oldu",
    "nooldu": "ne oldu",
    "nolmuş": "ne olmuş",
    "nolmus": "ne olmuş",
    "noluyo": "ne oluyor",
    "noluyor": "ne oluyor",
    "nolur": "ne olur",
    "bişey": "bir şey",
    "bisey": "bir şey",
    "bişi": "bir şey",
    "bisi": "bir şey",
    "bişiy": "bir şey",
    "bi şey": "bir şey",
    "herşey": "her şey",
    "hersey": "her şey",
    "hicbişey": "hiçbir şey",
    "hiçbişey": "hiçbir şey",
    "hicbirsey": "hiçbir şey",
    "hicbisi": "hiçbir şey",
    "hicbir": "hiçbir",
    "hicbi": "hiçbir",
    "herhangibir": "herhangi bir",
    "bi": "bir",
    "bida": "bir daha",
    "bidaha": "bir daha",
    "bi daha": "bir daha",
    "bikere": "bir kere",
    "bi kere": "bir kere",
    "bian": "bir an",
    "bi an": "bir an",
    "bigün": "bir gün",
    "bi gün": "bir gün",
    "biara": "bir ara",
    "bi ara": "bir ara",
    "bnc": "bence",
    "bnce": "bence",
    "bence": "bence",
    "sne": "sana",
    "bne": "ben",
    "snn": "senin",
    "bnm": "benim",
    "sn": "sen",
    "bn": "ben",
    "sz": "siz",
    "bz": "biz",
    "szin": "sizin",
    "bzm": "bizim",
    "cnm": "canım",
    "askm": "aşkım",
    "aşkm": "aşkım",
    "nreye": "nereye",
    "nrd": "nerede",
    "nerde": "nerede",
    "nerden": "nereden",
    "burda": "burada",
    "burdan": "buradan",
    "şurda": "şurada",
    "surda": "şurada",
    "orda": "orada",
    "ordan": "oradan",
    "içerde": "içeride",
    "icerde": "içeride",
    "dışarda": "dışarıda",
    "disarda": "dışarıda",
    "yukarda": "yukarıda",
    "ndn": "neden",
    "nie": "neden",
    "acb": "acaba",
    "acba": "acaba",
    "lutfen": "lütfen",
    "yha": "ya",
    "yhaa": "ya",
    "yhaaa": "ya",
    "valla": "doğrusu",
    "vallahi": "doğrusu",
    "harbi": "gerçekten",
    "harbiden": "gerçekten",
    "ciddili": "ciddi olarak",
    "aynen": "aynen",
    "ayn": "aynen",
    "aynn": "aynen",
    "pki": "peki",
    "pekı": "peki",
    "tmmdr": "tamamdır",
    "tamamdr": "tamamdır",
    "tmmdir": "tamamdır",
    "nssn": "nasılsın",
    "nslsn": "nasılsın",
    "nasısn": "nasılsın",
    "iyidr": "iyidir",
    "iydr": "iyidir",
    "ii": "iyi",
    "hç": "hiç",
    "skntı": "sıkıntı",
    "sknti": "sıkıntı",
    "skntı yok": "sorun yok",
    "sknti yok": "sorun yok",
    "sıkıntı yok": "sorun yok",
    "ö.d": "önemli değil",
    "kb": "kusura bakma",
    "k.b": "kusura bakma",
    "kusura bkma": "kusura bakma",
    "fln": "falan",
    "malesef": "maalesef",
    "yalnış": "yanlış",
    "yanlız": "yalnız",
    "herkez": "herkes",
    "orjinal": "orijinal",
    "tabi": "tabii",
    "tbi": "tabii",
    "tby": "tabii",

    # Question & intent contractions
    "napıyon": "ne yapıyorsun",
    "napiyon": "ne yapıyorsun",
    "napıyosun": "ne yapıyorsun",
    "napiyosun": "ne yapıyorsun",
    "napion": "ne yapıyorsun",
    "napıosun": "ne yapıyorsun",
    "napıyo": "ne yapıyor",
    "napiyo": "ne yapıyor",
    "napıyom": "ne yapıyorum",
    "napiyom": "ne yapıyorum",
    "napıyoz": "ne yapıyoruz",
    "napiyoz": "ne yapıyoruz",
    "napıyonuz": "ne yapıyorsunuz",
    "napiyonuz": "ne yapıyorsunuz",
    "napcan": "ne yapacaksın",
    "napıcan": "ne yapacaksın",
    "napcanız": "ne yapacaksınız",
    "napcak": "ne yapacak",
    "napcaz": "ne yapacağız",
    "napıcaz": "ne yapacağız",
    "napim": "ne yapayım",
    "napayım": "ne yapayım",
    "napmış": "ne yapmış",
    "napmis": "ne yapmış",
    "naptık": "ne yaptık",
    "naptik": "ne yaptık",
    "nolcak": "ne olacak",
    "nolucak": "ne olacak",
    "nolcaz": "ne olacağız",

    # Present continuous contractions (-yom, -yon, -yo, -yoz, -yolar)
    "geliyom": "geliyorum",
    "geliyon": "geliyorsun",
    "geliyo": "geliyor",
    "geliyoz": "geliyoruz",
    "geliyolar": "geliyorlar",
    "gelmiyom": "gelmiyorum",
    "gelmiyon": "gelmiyorsun",
    "gelmiyo": "gelmiyor",
    "gelmiyoz": "gelmiyoruz",
    "gidiyom": "gidiyorum",
    "gidiyon": "gidiyorsun",
    "gidiyo": "gidiyor",
    "gidiyoz": "gidiyoruz",
    "gidiyolar": "gidiyorlar",
    "gitmiyom": "gitmiyorum",
    "gitmiyon": "gitmiyorsun",
    "gitmiyo": "gitmiyor",
    "gitmiyoz": "gitmiyoruz",
    "yapıyom": "yapıyorum",
    "yapiyom": "yapıyorum",
    "yapıyon": "yapıyorsun",
    "yapiyon": "yapıyorsun",
    "yapıyo": "yapıyor",
    "yapiyo": "yapıyor",
    "yapıyoz": "yapıyoruz",
    "yapiyoz": "yapıyoruz",
    "yapıyolar": "yapıyorlar",
    "yapmıyom": "yapmıyorum",
    "yapmiom": "yapmıyorum",
    "yapmıyon": "yapmıyorsun",
    "yapmıyo": "yapmıyor",
    "yapmıyoz": "yapmıyoruz",
    "bakıyom": "bakıyorum",
    "bakıyon": "bakıyorsun",
    "bakıyo": "bakıyor",
    "bakıyoz": "bakıyoruz",
    "bakmıyom": "bakmıyorum",
    "bakmıyo": "bakmıyor",
    "görüyom": "görüyorum",
    "goruyom": "görüyorum",
    "görüyon": "görüyorsun",
    "goruyon": "görüyorsun",
    "görüyo": "görüyor",
    "goruyo": "görüyor",
    "görüyoz": "görüyoruz",
    "görmüyom": "görmüyorum",
    "görmüyo": "görmüyor",
    "biliyom": "biliyorum",
    "biliom": "biliyorum",
    "biliyon": "biliyorsun",
    "bilion": "biliyorsun",
    "biliyo": "biliyor",
    "bilio": "biliyor",
    "biliyoz": "biliyoruz",
    "bilmiyom": "bilmiyorum",
    "bilmiom": "bilmiyorum",
    "bilmiyon": "bilmiyorsun",
    "bilmiyo": "bilmiyor",
    "bilmiyoz": "bilmiyoruz",
    "istiyom": "istiyorum",
    "istiyon": "istiyorsun",
    "istiyo": "istiyor",
    "istiyoz": "istiyoruz",
    "istemiyom": "istemiyorum",
    "istemiyon": "istemiyorsun",
    "istemiyo": "istemiyor",
    "istemiyoz": "istemiyoruz",
    "diyom": "diyorum",
    "diyon": "diyorsun",
    "diyo": "diyor",
    "diyoz": "diyoruz",
    "demiyom": "demiyorum",
    "demiyo": "demiyor",
    "duyuyom": "duyuyorum",
    "duyuyon": "duyuyorsun",
    "duyuyo": "duyuyor",
    "duymuyom": "duymuyorum",
    "duymuyo": "duymuyor",
    "alıyom": "alıyorum",
    "aliyom": "alıyorum",
    "alıyon": "alıyorsun",
    "alıyo": "alıyor",
    "alıyoz": "alıyoruz",
    "almıyom": "almıyorum",
    "veriyom": "veriyorum",
    "veriyon": "veriyorsun",
    "veriyo": "veriyor",
    "veriyoz": "veriyoruz",
    "vermiyom": "vermiyorum",
    "ediyom": "ediyorum",
    "ediyon": "ediyorsun",
    "ediyo": "ediyor",
    "ediyoz": "ediyoruz",
    "etmiyom": "etmiyorum",
    "oluyom": "oluyorum",
    "oluyon": "oluyorsun",
    "oluyo": "oluyor",
    "oluyoz": "oluyoruz",
    "olmuyom": "olmuyorum",
    "olmuyo": "olmuyor",
    "anlıyom": "anlıyorum",
    "anliyom": "anlıyorum",
    "anlıyon": "anlıyorsun",
    "anlıyo": "anlıyor",
    "anlıyoz": "anlıyoruz",
    "anlamıyom": "anlamıyorum",
    "anlamıyo": "anlamıyor",
    "sanıyom": "sanıyorum",
    "sanıyon": "sanıyorsun",
    "sanıyo": "sanıyor",
    "duruyom": "duruyorum",
    "duruyon": "duruyorsun",
    "kalıyom": "kalıyorum",
    "kalıyon": "kalıyorsun",
    "bekliyom": "bekliyorum",
    "bekliyon": "bekliyorsun",
    "çalışıyom": "çalışıyorum",
    "calisiyom": "çalışıyorum",
    "çalışıyon": "çalışıyorsun",
    "oturuyom": "oturuyorum",
    "oturuyon": "oturuyorsun",
    "konuşuyom": "konuşuyorum",
    "konusuyom": "konuşuyorum",
    "konuşuyon": "konuşuyorsun",
    "okuyom": "okuyorum",
    "okuyon": "okuyorsun",
    "yazıyom": "yazıyorum",
    "yazıyon": "yazıyorsun",
    "seviyom": "seviyorum",
    "seviyon": "seviyorsun",
    "düşünüyom": "düşünüyorum",
    "dusunuyom": "düşünüyorum",
    "düşünüyon": "düşünüyorsun",
    "kaçıyom": "kaçıyorum",
    "atıyom": "atıyorum",
    "buluyom": "buluyorum",
    "bulamıyo": "bulamıyor",
    "yapamıyo": "yapamıyor",
    "gelemiyo": "gelemiyor",
    "gidemiyo": "gidemiyor",
    "yapamıyom": "yapamıyorum",
    "gelemiyom": "gelemiyorum",
    "gidemiyom": "gidemiyorum",

    # Future tense contractions (-cam, -cem, -cak, -cek, -caz, -cez, -can, -cen)
    "yapcam": "yapacağım",
    "yapıcam": "yapacağım",
    "yapicam": "yapacağım",
    "yapcan": "yapacaksın",
    "yapıcan": "yapacaksın",
    "yapcak": "yapacak",
    "yapıcak": "yapacak",
    "yapcaz": "yapacağız",
    "yapıcaz": "yapacağız",
    "yapmıycam": "yapmayacağım",
    "yapmaycam": "yapmayacağım",
    "yapmıycak": "yapmayacak",
    "yapmıycaz": "yapmayacağız",
    "gelcem": "geleceğim",
    "gelicem": "geleceğim",
    "gelcen": "geleceksin",
    "gelicen": "geleceksin",
    "gelcek": "gelecek",
    "gelicek": "gelecek",
    "gelcez": "geleceğiz",
    "gelicez": "geleceğiz",
    "gelmiycam": "gelmeyeceğim",
    "gelmeycem": "gelmeyeceğim",
    "gelmiycem": "gelmeyeceğim",
    "gitcem": "gideceğim",
    "gidicem": "gideceğim",
    "gitcen": "gideceksin",
    "gidicen": "gideceksin",
    "gitcek": "gidecek",
    "gidicek": "gidecek",
    "gitcez": "gideceğiz",
    "gidicez": "gideceğiz",
    "gitmiycam": "gitmeyeceğim",
    "gitmeycem": "gitmeyeceğim",
    "gitmiycem": "gitmeyeceğim",
    "etcem": "edeceğim",
    "edicem": "edeceğim",
    "etcen": "edeceksin",
    "edicen": "edeceksin",
    "etcek": "edecek",
    "edicek": "edecek",
    "etcik": "edecek",
    "etcaz": "edeceğiz",
    "edicez": "edeceğiz",
    "etmiycam": "etmeyeceğim",
    "etmeycem": "etmeyeceğim",
    "alcam": "alacağım",
    "alıcam": "alacağım",
    "alicam": "alacağım",
    "alcan": "alacaksın",
    "alıcan": "alacaksın",
    "alcak": "alacak",
    "alıcak": "alacak",
    "alcaz": "alacağız",
    "alıcaz": "alacağız",
    "almıycam": "almayacağım",
    "vercem": "vereceğim",
    "vericem": "vereceğim",
    "vercen": "vereceksin",
    "vericen": "vereceksin",
    "vercek": "verecek",
    "vericek": "verecek",
    "vercez": "vereceğiz",
    "vericez": "vereceğiz",
    "vermiycam": "vermeyeceğim",
    "bakcam": "bakacağım",
    "bakıcam": "bakacağım",
    "bakcan": "bakacaksın",
    "bakıcan": "bakacaksın",
    "bakcak": "bakacak",
    "bakıcak": "bakacak",
    "bakcaz": "bakacağız",
    "bakıcaz": "bakacağız",
    "görcem": "göreceğim",
    "görücem": "göreceğim" if True else "göreceğim",
    "gorcem": "göreceğim",
    "görcen": "göreceksin",
    "görcek": "görecek",
    "görcez": "göreceğiz",
    "olcam": "olacağım",
    "olucam": "olacağım",
    "olcan": "olacaksın",
    "olucan": "olacaksın",
    "olcak": "olacak",
    "olucak": "olacak",
    "olcaz": "olacağız",
    "olucaz": "olacağız",
    "bulcam": "bulacağım",
    "bulucam": "bulacağım",
    "bulcan": "bulacaksın",
    "bulcak": "bulacak",
    "durcam": "duracağım",
    "durucam": "duracağım",
    "kalcam": "kalacağım",
    "kalıcam": "kalacağım",
    "bilcem": "bileceğim",
    "bilicem": "bileceğim",
}

# ---------------------------------------------------------------------------
# Address & Vocative Terms (Hitaplar ve Sokak Dili)
# ---------------------------------------------------------------------------
# Always vocative slang words (safe to remove or neutralize globally)
ALWAYS_VOCATIVE_WORDS: Set[str] = {
    "kanka", "knk", "kankam", "kankito", "kanks", "kardo",
    "bro", "brom", "brother", "moruk", "moruq",
    "aga", "agam", "agacım",
    "lan", "len", "ulan", "ula",
    "olum", "oğlum", "oglum", "olm",
    "kirve", "bilader", "birader", "kardeş", "kardes",
}

# Contextual address words (may also be valid nouns in non-address contexts)
# e.g. "Benim babam", "İngiltere kralı", "Dayım geldi" vs "Dayı naber", "Kral adamsın"
CONTEXTUAL_VOCATIVE_WORDS: Set[str] = {
    "reis", "kral", "hocam", "dayı", "baba",
}

# Neutral equivalents if address_action == "neutralize"
ADDRESS_NEUTRAL_MAP: Dict[str, str] = {
    "kanka": "arkadaşım",
    "knk": "arkadaşım",
    "kankam": "arkadaşım",
    "kardo": "arkadaşım",
    "bro": "arkadaşım",
    "brom": "arkadaşım",
    "moruk": "arkadaşım",
    "aga": "arkadaşım",
    "agam": "arkadaşım",
    "reis": "yetkili",
    "kral": "değerli insan",
    "hocam": "yetkili",
    "dayı": "beyefendi",
    "baba": "beyefendi",
    "birader": "arkadaşım",
    "bilader": "arkadaşım",
    "kirve": "arkadaşım",
    "olum": "arkadaşım",
    "oğlum": "arkadaşım",
    "olm": "arkadaşım",
    # Particles that have no polite replacement are dropped even in neutralize mode
    "lan": "",
    "len": "",
    "ulan": "",
    "ula": "",
    "ya": "",
}

# ---------------------------------------------------------------------------
# Profanity, Insult & Vulgar Slang Neutralization Dictionary
# ---------------------------------------------------------------------------
# Multi-word phrases & idioms (matched first, longest first)
PROFANITY_PHRASE_MAP: Dict[str, str] = {
    "siktir git": "buradan uzaklaş",
    "siktir ol git": "buradan uzaklaş",
    "siktir et": "boş ver",
    "siktir çekti": "reddetti",
    "siktir çektim": "reddettim",
    "hasiktir": "hadi oradan",
    "hassiktir": "hadi oradan",
    "sike sike": "zorunlu olarak",
    "amına koyayım": "",
    "amına koyim": "",
    "amına koydugum": "uygunsuz kimse",
    "amına koyduğum": "uygunsuz kimse",
    "amına kodumun": "söz konusu",
    "amk ya": "",
    "ananı sikeyim": "[uygunsuz ifade]",
    "ananın amı": "[uygunsuz ifade]",
    "orospu çocuğu": "ahlaksız kimse",
    "orospu cocugu": "ahlaksız kimse",
    "orospu çocukları": "ahlaksız kimseler",
    "orospu çocukluğu": "ahlaksızlık",
    "döl israfı": "faydasız kişi",
    "bok gibi": "çok kötü",
    "bok gibiydi": "çok kötüydü",
    "yarrak gibi": "çok kötü",
    "yarak gibi": "çok kötü",
    "taşşak geçmek": "alay etmek",
    "taşşak geçme": "alay etme",
    "taşak geçmek": "alay etmek",
    "taşak geçme": "alay etme",
    "daşşak geçmek": "alay etmek",
    "sikimde değil": "umurumda değil",
    "sikinde değil": "umurunda değil",
    "yarrak yedin": "büyük hata yaptın",
    "bok yedin": "hata yaptın",
    "bok yemek": "hata yapmak",
    "götü yememek": "cesaret edememek",
    "götün yemedi": "cesaret edemedin",
    "göt olmak": "mahcup olmak",
    "göt oldu": "mahcup oldu",
    "göt etmek": "mahcup etmek",
    "göt etti": "mahcup etti",
    "kafana sıçarım": "sana çok kızarım",
    "ağzına sıçayım": "seni kınıyorum",
    "ağzına sıçarım": "sana çok kızarım",
    "aptal herif": "düşüncesiz kişi",
    "salak herif": "düşüncesiz kişi",
    "gerizekalı herif": "anlayışsız kişi",
}

# Single words (slang profanity & insults -> polite/neutral forms)
PROFANITY_WORD_MAP: Dict[str, str] = {
    # Coarse profanity & fillers
    "amk": "",
    "aq": "",
    "amq": "",
    "a.q": "",
    "a.m.k": "",
    "oç": "ahlaksız kimse",
    "o.ç": "ahlaksız kimse",
    "o.ç.": "ahlaksız kimse",
    "siktir": "hadi oradan",
    "sg": "uzaklaş",
    "sktir": "hadi oradan",
    "s*ktir": "hadi oradan",
    "a**k": "",
    "orospu": "ahlaksız kimse",
    "piç": "saygısız kimse",
    "pic": "saygısız kimse",
    "yavşak": "güvenilmez kimse",
    "yavsak": "güvenilmez kimse",
    "puşt": "kötü niyetli kimse",
    "pust": "kötü niyetli kimse",
    "ibne": "güvenilmez kimse",
    "göt": "arka",
    "götveren": "kötü niyetli kişi",
    "götlek": "korkak kimse",
    "yarrak": "kötü durum",
    "yarak": "kötü durum",
    "yarrk": "kötü durum",
    "amcık": "kaba söz",
    "amcik": "kaba söz",
    "taşşak": "alay",
    "taşak": "alay",
    "daşşak": "alay",
    "kahpe": "hain kişi",
    "sürtük": "uygunsuz kişi",
    "surtuk": "uygunsuz kişi",
    "fahişe": "uygunsuz kişi",
    "fahise": "uygunsuz kişi",
    "pezevenk": "aracı kimse",
    "gavat": "onursuz kişi",
    "kancık": "hain kişi",
    "kancik": "hain kişi",
    "sikik": "bozuk",
    "siktim": "cezalandırdım",
    "sikerim": "hesap sorarım",
    "sikeyim": "kınıyorum",
    "sikti": "zarara uğrattı",
    "sıkik": "bozuk",
    "bok": "kötü durum",
    "b*k": "kötü durum",
    "boktan": "kötü",
    "sıçtık": "zor duruma düştük" if True else "zor duruma düştük",
    "sictik": "zor duruma düştük",
    "sıçtın": "zor duruma düştün",
    "sictin": "zor duruma düştün",
    "sıçtı": "zor duruma düştü",
    "sicti": "zor duruma düştü",

    # Insults & mild derogatory slurs
    "salak": "düşüncesiz",
    "salakça": "düşüncesizce",
    "aptal": "düşüncesiz",
    "aptalca": "düşüncesizce",
    "gerizekalı": "anlayışsız",
    "gerizekali": "anlayışsız",
    "ahmak": "düşüncesiz",
    "enayi": "kolay aldanan",
    "dangalak": "düşüncesiz kimse",
    "mankafa": "anlayışsız kimse",
    "keriz": "kolay aldanan",
    "hıyar": "kaba kimse",
    "hiyar": "kaba kimse",
    "hırbo": "kaba kimse",
    "hirbo": "kaba kimse",
    "dallama": "saygısız kimse",
    "öküz": "kaba kimse",
    "okuz": "kaba kimse",
    "ayı": "kaba kimse",
    "ayi": "kaba kimse",
    "andaval": "anlayışsız kimse",
    "beyinsiz": "düşüncesiz kimse",
    "denyo": "dengesiz kimse",
    "denyolu": "dengesiz kimse",
    "lavuk": "laubali kimse",
    "sünepe": "pısırık kimse",
    "sunepe": "pısırık kimse",
    "serseri": "başıboş kimse",
    "şerefsiz": "onursuz kimse",
    "serefsiz": "onursuz kimse",
    "haysiyetsiz": "saygısız kimse",
    "karaktersiz": "güvenilmez kimse",
    "namussuz": "dürüst olmayan kimse",
    "kansız": "merhametsiz kimse",
    "kansiz": "merhametsiz kimse",
    "alçak": "kötü niyetli kimse",
    "alcak": "kötü niyetli kimse",
    "çomar": "bağnaz kimse",
    "comar": "bağnaz kimse",
}


# ---------------------------------------------------------------------------
# TextNeutralizer Class
# ---------------------------------------------------------------------------
class TextNeutralizer:
    """Turkish Text Style and Identity Neutralizer.

    Neutralizes stylometric fingerprints, internet slang, colloquialisms,
    character elongations, excessive punctuation, and profanity in Turkish text.
    """

    def __init__(
        self,
        clean_elongations: bool = True,
        clean_punct: bool = True,
        normalize_case: bool = True,
        replace_slang: bool = True,
        remove_addresses: bool = True,
        neutralize_profanities: bool = True,
        profanity_mode: str = "neutralize",  # 'neutralize', 'mask', 'remove'
        address_action: str = "remove",       # 'remove', 'neutralize'
    ) -> None:
        self.clean_elongations = clean_elongations
        self.clean_punct = clean_punct
        self.normalize_case = normalize_case
        self.replace_slang = replace_slang
        self.remove_addresses = remove_addresses
        self.neutralize_profanities = neutralize_profanities
        self.profanity_mode = profanity_mode
        self.address_action = address_action

        self._build_compiled_patterns()

    def _build_compiled_patterns(self) -> None:
        """Pre-compile regex patterns for high-performance processing."""
        # 1. Profanity multi-word patterns
        sorted_phrases = sorted(PROFANITY_PHRASE_MAP.keys(), key=len, reverse=True)
        phrase_regex = r"(?<!\w)(" + "|".join(re.escape(k) for k in sorted_phrases) + r")(?!\w)"
        self._profanity_phrase_pattern = re.compile(phrase_regex, re.IGNORECASE)

        # 2. Profanity single word patterns
        sorted_words = sorted(PROFANITY_WORD_MAP.keys(), key=len, reverse=True)
        word_regex = r"(?<!\w)(" + "|".join(re.escape(k) for k in sorted_words) + r")(?!\w)"
        self._profanity_word_pattern = re.compile(word_regex, re.IGNORECASE)

        # 3. Slang and shorthands patterns
        sorted_slang = sorted(SLANG_AND_SHORTHAND_MAP.keys(), key=len, reverse=True)
        slang_regex = r"(?<!\w)(" + "|".join(re.escape(k) for k in sorted_slang) + r")(?!\w)"
        self._slang_pattern = re.compile(slang_regex, re.IGNORECASE)

        # 4. Always-vocative address pattern
        sorted_vocatives = sorted(ALWAYS_VOCATIVE_WORDS, key=len, reverse=True)
        voc_regex = r"(?<!\w)(" + "|".join(re.escape(k) for k in sorted_vocatives) + r")(?!\w)"
        self._vocative_pattern = re.compile(voc_regex, re.IGNORECASE)

    # -----------------------------------------------------------------------
    # 1. Karakter Uzatma Temizleyici (Character Elongation)
    # -----------------------------------------------------------------------
    def clean_elongated_chars(self, text: str) -> str:
        """Prunes repeated characters occurring more than twice consecutively.

        Examples:
            'lütfeeeen' -> 'lütfen'
            'nolurrrr'  -> 'ne olur'
            'yhaaa'     -> 'ya'
        """
        if not text:
            return ""

        def _reduce_word(match: re.Match) -> str:
            word = match.group(0)
            lower_word = tr_lower(word)

            # Direct mapping if known elongated form
            if lower_word in ELONGATED_STEM_MAP:
                rep = ELONGATED_STEM_MAP[lower_word]
                return tr_capitalize(rep) if word[0].isupper() else rep

            # Collapse 3 or more consecutive identical characters
            # Check if reducing to 2 matches a known double-letter word (e.g. 'saat')
            candidate_two = re.sub(r"([a-zA-ZçğıöşüÇĞİÖŞÜ])\1{2,}", r"\1\1", lower_word)
            if candidate_two in DOUBLE_LETTER_WORDS:
                reduced_lower = candidate_two
            else:
                candidate_one = re.sub(r"([a-zA-ZçğıöşüÇĞİÖŞÜ])\1{2,}", r"\1", lower_word)
                reduced_lower = candidate_one

            # Check if reduced form maps to an elongated stem (e.g. 'nolur' -> 'ne olur', 'yha' -> 'ya')
            if reduced_lower in ELONGATED_STEM_MAP:
                rep = ELONGATED_STEM_MAP[reduced_lower]
                return tr_capitalize(rep) if word[0].isupper() else rep

            # Preserve capitalization of original
            if word.isupper() and len(word) > 1:
                return tr_upper(reduced_lower)
            elif word[0].isupper():
                return tr_capitalize(reduced_lower)
            return reduced_lower

        # Process words with 3 or more consecutive letters
        text = re.sub(r"\b\w*([a-zA-ZçğıöşüÇĞİÖŞÜ])\1{2,}\w*\b", _reduce_word, text)

        # Normalize common laugh tracks (hahaha..., sjsjsj..., jajaja...)
        text = re.sub(r"\b(ha){3,}h?\b", "haha", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(ah){3,}a?\b", "haha", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(sj){3,}s?\b", "haha", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(ja){3,}j?\b", "haha", text, flags=re.IGNORECASE)

        return text

    # -----------------------------------------------------------------------
    # 2. Noktalama ve Boşluk Temizliği (Punctuation and Spacing)
    # -----------------------------------------------------------------------
    def clean_punctuation(self, text: str) -> str:
        """Normalizes excessive question marks, exclamation marks, and dots.

        Examples:
            '???!!!' -> '?'
            '.....'  -> '.'
            '!!!!!'  -> '!'
        """
        if not text:
            return ""

        # Mixed question and exclamation marks (prioritize '?' as in ???!!! -> ?)
        text = re.sub(r"[?!]{2,}", lambda m: "?" if "?" in m.group(0) else "!", text)

        # Repeated dots (5 dots or more, or 2 or more dots -> single '.')
        text = re.sub(r"\.{2,}", ".", text)

        # Repeated commas, colons, semicolons
        text = re.sub(r",{2,}", ",", text)
        text = re.sub(r";{2,}", ";", text)

        # Clean spaces before punctuation
        text = re.sub(r"\s+([,.:;?!])", r"\1", text)

        # Clean multiple spaces
        text = re.sub(r"[ \t]{2,}", " ", text)

        # Clean duplicate adjacent punctuation marks (e.g. ',.' or '.,')
        text = re.sub(r"([.!?])[,]+", r"\1", text)
        text = re.sub(r"[,]+([.!?])", r"\1", text)

        # Clean leading punctuation from text / lines
        text = re.sub(r"^\s*[,;:]\s*", "", text)

        return text.strip()

    # -----------------------------------------------------------------------
    # 3. Büyük-Küçük Harf Normalizasyonu (Casing Normalization)
    # -----------------------------------------------------------------------
    def normalize_casing(self, text: str) -> str:
        """Converts alternating caps ('bÖyLe yAzI') or ALL CAPS to proper sentence case."""
        if not text:
            return ""

        def _fix_sentence(s: str) -> str:
            if not s:
                return s

            alphas = [c for c in s if c.isalpha()]
            # If all letters are uppercase and sentence length is substantial -> ALL CAPS screaming
            if len(alphas) >= 3 and all(c.isupper() for c in alphas):
                s = tr_lower(s)
            else:
                # Replace individually irregular words (e.g. 'bÖyLe', 'yAzI')
                tokens = re.split(r"(\W+)", s)
                s = "".join(tr_lower(t) if is_irregular_casing(t) else t for t in tokens)

            # Capitalize the first alphabetic character of the sentence
            for i, c in enumerate(s):
                if c.isalpha():
                    return s[:i] + tr_upper(c) + s[i + 1:]
            return s

        # Process line by line, and sentence by sentence
        lines = text.split("\n")
        normalized_lines: List[str] = []

        for line in lines:
            if not line.strip():
                normalized_lines.append(line)
                continue

            # Split on sentence boundary punctuation: . ! ?
            parts = re.split(r"([.!?]+\s*)", line)
            sentence_res: List[str] = []
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    sentence_res.append(_fix_sentence(part))
                else:
                    sentence_res.append(part)
            normalized_lines.append("".join(sentence_res))

        return "\n".join(normalized_lines)

    # -----------------------------------------------------------------------
    # 4. Küfür ve Hakaret Dönüştürücü / Sansürleyici (Profanity Sanitizer)
    # -----------------------------------------------------------------------
    def sanitize_profanity(self, text: str) -> str:
        """Detects and neutralizes Turkish profanity, vulgarity, and insults."""
        if not text:
            return ""

        mode = self.profanity_mode

        def _phrase_replacer(match: re.Match) -> str:
            original = match.group(0)
            key = tr_lower(original)
            target = PROFANITY_PHRASE_MAP.get(key)
            if target is None:
                return original

            if mode == "remove":
                return ""
            elif mode == "mask":
                words = original.split()
                masked_words = []
                for w in words:
                    if len(w) <= 2:
                        masked_words.append("*" * len(w))
                    else:
                        masked_words.append(w[0] + "*" * (len(w) - 2) + w[-1])
                return " ".join(masked_words)
            else:  # 'neutralize'
                if not target:
                    return ""
                return tr_capitalize(target) if original[0].isupper() else target

        def _word_replacer(match: re.Match) -> str:
            original = match.group(0)
            key = tr_lower(original)
            target = PROFANITY_WORD_MAP.get(key)
            if target is None:
                return original

            if mode == "remove":
                return ""
            elif mode == "mask":
                if len(original) <= 2:
                    return "*" * len(original)
                return original[0] + "*" * (len(original) - 2) + original[-1]
            else:  # 'neutralize'
                if not target:
                    return ""
                return tr_capitalize(target) if original[0].isupper() else target

        # 1. Multi-word profanities & phrases first
        text = self._profanity_phrase_pattern.sub(_phrase_replacer, text)
        # 2. Single word profanities
        text = self._profanity_word_pattern.sub(_word_replacer, text)

        return text

    # -----------------------------------------------------------------------
    # 5. Sokak Dili ve Hitap Dönüştürücü (Address / Vocative Terms)
    # -----------------------------------------------------------------------
    def remove_address_terms(self, text: str) -> str:
        """Removes or neutralizes informal street address terms ('kanka', 'bro', 'reis', etc.)."""
        if not text:
            return ""

        action = self.address_action

        # Handle 'ya' as a filler / vocative:
        # Avoid removing 'ya' when part of conjunction 'ya da' or 'ya da ...'
        def _clean_ya(t: str) -> str:
            # Protect 'ya da' with placeholder
            t = re.sub(r"\bya\s+da\b", "__YA_DA_CONJUNCTION__", t, flags=re.IGNORECASE)
            # Remove standalone filler 'ya' at beginning or end or with punctuation
            t = re.sub(r"^\s*ya\s+", "", t, flags=re.IGNORECASE)
            t = re.sub(r"\s+ya(?=\s*[,.!?]|$)", "", t, flags=re.IGNORECASE)
            t = re.sub(r"[,]\s*ya\b", "", t, flags=re.IGNORECASE)
            t = re.sub(r"\bya\s*[,]", "", t, flags=re.IGNORECASE)
            # Common fillers like 'off ya', 'yeter ya', 'bırak ya', 'yapma ya'
            t = re.sub(r"\b(off|of|yeter|bırak|yapma|olmaz|yok)\s+ya\b", r"\1", t, flags=re.IGNORECASE)
            # Restore 'ya da'
            t = t.replace("__YA_DA_CONJUNCTION__", "ya da")
            return t

        text = _clean_ya(text)

        # 1. Handle ALWAYS vocative words: kanka, bro, moruk, aga, lan, olum, etc.
        def _vocative_replacer(match: re.Match) -> str:
            original = match.group(0)
            key = tr_lower(original)
            if action == "neutralize":
                rep = ADDRESS_NEUTRAL_MAP.get(key, "")
                if not rep:
                    return ""
                return tr_capitalize(rep) if original[0].isupper() else rep
            else:  # 'remove'
                return ""

        text = self._vocative_pattern.sub(_vocative_replacer, text)

        # 2. Handle contextual vocatives: reis, kral, hocam, dayı, baba
        # Only treat as vocative if at start/end of sentence, or near punctuation,
        # or followed by question/greeting/command words.
        for word in CONTEXTUAL_VOCATIVE_WORDS:
            replacement = ADDRESS_NEUTRAL_MAP.get(word, "") if action == "neutralize" else ""

            # Isolated between punctuation or at boundaries
            patterns = [
                # Sentence start vocative: e.g. "Dayı sakin ol", "Reis naber"
                rf"^\s*{word}\s+",
                # Trailing vocative: e.g. "Sakin ol dayı.", "Nasılsın reis?"
                rf"\s+{word}(?=\s*[,.!?]|$)",
                # Comma enclosed: e.g. ", dayı,", ", reis,"
                rf"[,]\s*{word}\s*[,]",
                rf"[,]\s*{word}\b",
                rf"\b{word}\s*[,]",
            ]
            for p in patterns:
                if action == "neutralize" and replacement:
                    text = re.sub(p, f" {replacement} ", text, flags=re.IGNORECASE)
                else:
                    text = re.sub(p, " ", text, flags=re.IGNORECASE)

        return text

    # -----------------------------------------------------------------------
    # 6. Kısaltma ve Mesajlaşma Argoları (Slang & Shorthands)
    # -----------------------------------------------------------------------
    def replace_slang_and_shorthands(self, text: str) -> str:
        """Converts chat shorthand abbreviations and colloquial verb contractions to standard Turkish."""
        if not text:
            return ""

        def _slang_replacer(match: re.Match) -> str:
            original = match.group(0)
            key = tr_lower(original)
            target = SLANG_AND_SHORTHAND_MAP.get(key)
            if target is None:
                return original

            # Preserve title / sentence capitalization
            if original.isupper() and len(original) > 1:
                return tr_upper(target)
            elif original[0].isupper():
                return tr_capitalize(target)
            return target

        return self._slang_pattern.sub(_slang_replacer, text)

    # -----------------------------------------------------------------------
    # Class-level Convenience Methods
    # -----------------------------------------------------------------------
    @classmethod
    def clean_elongated_characters(cls, text: str) -> str:
        return cls().clean_elongated_chars(text)

    @classmethod
    def normalize_punctuation(cls, text: str) -> str:
        return cls().clean_punctuation(text)

    @classmethod
    def sanitize_profanity_and_slang(cls, text: str) -> str:
        inst = cls()
        t = inst.sanitize_profanity(text)
        return inst.replace_slang_and_shorthands(t)

    @classmethod
    def remove_street_vocatives(cls, text: str) -> str:
        return cls().remove_address_terms(text)

    @classmethod
    def normalize_sentence_casing(cls, text: str) -> str:
        return cls().normalize_casing(text)

    # -----------------------------------------------------------------------
    # 7. Ana Nötrleme Fonksiyonu (Master Neutralize Pipeline)
    # -----------------------------------------------------------------------
    def neutralize(self, text: str = None) -> str:
        """Full neutralization pipeline for Turkish text.
        Supports both instance call: neutralizer.neutralize(text)
        and class call: TextNeutralizer.neutralize(text)
        """
        # Handle invocation as class method: TextNeutralizer.neutralize("some text")
        if isinstance(self, str) and text is None:
            return TextNeutralizer().neutralize(self)

        if not text or not text.strip():
            return ""

        # Step 1: Character elongations
        if self.clean_elongations:
            text = self.clean_elongated_chars(text)

        # Step 2: Excessive punctuation normalization (first pass)
        if self.clean_punct:
            text = self.clean_punctuation(text)

        # Step 3: Profanity & insult neutralization
        if self.neutralize_profanities:
            text = self.sanitize_profanity(text)

        # Step 4: Address / vocative slang removal or neutralization
        if self.remove_addresses:
            text = self.remove_address_terms(text)

        # Step 5: Chat shorthands & colloquialisms replacement
        if self.replace_slang:
            text = self.replace_slang_and_shorthands(text)

        # Step 6: Clean up punctuation and spacing after removals
        if self.clean_punct:
            text = self.clean_punctuation(text)

        # Step 7: Sentence casing normalization
        if self.normalize_case:
            text = self.normalize_casing(text)

        return text.strip()


# Convenience function for quick calls
def neutralize(text: str, **kwargs) -> str:
    """Convenience helper to neutralize Turkish text using default TextNeutralizer settings."""
    neutralizer = TextNeutralizer(**kwargs)
    return neutralizer.neutralize(text)
