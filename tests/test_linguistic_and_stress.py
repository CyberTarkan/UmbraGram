"""Linguistic Neutralization, Database Concurrency, and Spam Flood Stress Tests.

Tests:
1. Turkish linguistic neutralization stress under 165+ realistic street language,
   slang, severe profanity, exaggerated character elongations, colloquial abbreviations,
   irregular casing, and ensures Turkish character integrity and exact URL and emoji preservation.
2. Database concurrency stress under 100 concurrent threads performing simultaneous
   inserts, reads, updates, and deletes with zero database locked errors or race conditions.
3. Spam and flood protection under high-frequency bombardments (50 msgs/s) and album
   burst uploads with graduated penalties (temporary cooldown -> permanent block).
"""

import os
import re
import time
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
import pytest

from text_neutralizer import TextNeutralizer, tr_lower
from db_manager import DatabaseManager
from spam_protector import SpamProtector


# ===========================================================================
# 1. Linguistic & Text Neutralization Stress Suite (165+ Diverse Inputs)
# ===========================================================================

STRESS_LINGUISTIC_DATASET: List[Tuple[str, List[str], List[str], List[str]]] = [
    # Format: (input_text, expected_in_output, forbidden_in_output, preserved_entities)

    # --- 1-25: Exaggerated elongations & street vocatives ---
    ("ayyyyynen reiiisss", ["Aynen"], ["ayyyyynen", "reiiisss"], []),
    ("lütfeeeen bana bişey söyler misin ya", ["Lütfen", "bir şey"], ["lütfeeeen", "bişey"], []),
    ("nolurrrr yardım et kanka", ["Ne olur", "yardım"], ["nolurrrr", "kanka"], []),
    ("yhaaa sen de bi alemsin valla", ["bir", "doğrusu"], ["yhaaa", "valla"], []),
    ("çoook teşekkürler broooo", ["Çok", "teşekkürler"], ["çoook", "broooo"], []),
    ("offff sıkıldım yaaa", ["Of", "sıkıldım"], ["offff", "yaaa"], []),
    ("güzeeeel kardeşim benim", ["Güzel"], ["güzeeeel"], []),
    ("tamammmm anladım ben seni", ["Tamam", "anladım"], ["tamammmm"], []),
    ("pekkkki öyle olsun bakalım", ["Peki", "öyle olsun"], ["pekkkki"], []),
    ("selaaam nbr nasılsın", ["Selam", "ne haber", "nasılsın"], ["selaaam", "nbr"], []),
    ("harikaaa bir haber bu", ["Harika", "bir haber"], ["harikaaa"], []),
    ("merhabaaa ahbap naptın", ["Merhaba", "ne yaptın"], ["merhabaaa", "naptın"], []),
    ("süpeeeer oldu bu iş", ["Süper", "oldu"], ["süpeeeer"], []),
    ("evveeeet sonunda bitti", ["Evet", "sonunda bitti"], ["evveeeet"], []),
    ("hayıııır öyle bir şey yok", ["Hayır", "öyle bir şey yok"], ["hayıııır"], []),
    ("ayyyyyyynen öyle valla", ["Aynen", "öyle", "doğrusu"], ["ayyyyyyynen", "valla"], []),
    ("nolurrr bi baksana buraya", ["Ne olur", "bir baksana"], ["nolurrr", " bi "], []),
    ("çooook zor durumdayım", ["Çok", "zor durumdayım"], ["çooook"], []),
    ("tamamm hallederiz skntı yok", ["Tamam", "sorun yok"], ["tamamm", "skntı yok"], []),
    ("lütfeen geri dön artık", ["Lütfen", "geri dön"], ["lütfeen"], []),
    ("kankaaa nerdesin sen ya", ["Neredesin"], ["kankaaa"], []),
    ("brooo hemen gel buraya", ["Hemen gel buraya"], ["brooo"], []),
    ("agammm sen bilirsin işi", ["Sen bilirsin"], ["agammm"], []),
    ("moruq naptın sen öyle", ["Ne yaptın"], ["moruq", "naptın"], []),
    ("kirvem nasılsın iyi misin", ["Nasılsın", "iyi misin"], ["kirvem"], []),

    # --- 26-55: Colloquial contractions & verb forms ---
    ("napıon şimdi sen", ["Ne yapıyorsun", "şimdi sen"], ["napıon"], []),
    ("geliyom bekle iki dakka", ["Geliyorum", "bekle"], ["geliyom"], []),
    ("napiyon oralarda", ["Ne yapıyorsun", "oralarda"], ["napiyon"], []),
    ("gidiyom ben haberin olsun", ["Gidiyorum", "ben"], ["gidiyom"], []),
    ("napıosun moruk", ["Ne yapıyorsun"], ["napıosun", "moruk"], []),
    ("napıyo bu adamlar", ["Ne yapıyor", "bu adamlar"], ["napıyo"], []),
    ("napıyom ben burada bilmiyom", ["Ne yapıyorum", "bilmiyorum"], ["napıyom", "bilmiyom"], []),
    ("napıoz bu akşam", ["Ne yapıyoruz", "bu akşam"], ["napıoz"], []),
    ("napıonuz gençler", ["Ne yapıyorsunuz", "gençler"], ["napıonuz"], []),
    ("nabıyon nasılsın", ["Ne yapıyorsun", "nasılsın"], ["nabıyon"], []),
    ("nabıon ne var ne yok", ["Ne yapıyorsun", "ne var"], ["nabıon"], []),
    ("nörüyon hemşerim", ["Ne yapıyorsun"], ["nörüyon"], []),
    ("napcan şimdi söyle bakalım", ["Ne yapacaksın", "şimdi söyle"], ["napcan"], []),
    ("napıcan bu parayla", ["Ne yapacaksın", "bu parayla"], ["napıcan"], []),
    ("napcaz biz seninle", ["Ne yapacağız", "biz seninle"], ["napcaz"], []),
    ("napıcaz bu durumu", ["Ne yapacağız", "bu durumu"], ["napıcaz"], []),
    ("napim elimden bir şey gelmiyor", ["Ne yapayım", "elimden bir şey gelmiyor"], ["napim"], []),
    ("nolcak bizim halimiz", ["Ne olacak", "bizim halimiz"], ["nolcak"], []),
    ("nolucak bu işin sonu", ["Ne olacak", "bu işin sonu"], ["nolucak"], []),
    ("noldu anlat hele", ["Ne oldu", "anlat hele"], ["noldu"], []),
    ("geliyon mu bizimle", ["Geliyorsun", "bizimle"], ["geliyon"], []),
    ("geliyo musun buraya", ["Geliyor", "buraya"], ["geliyo"], []),
    ("geliyolar şimdi", ["Geliyorlar", "şimdi"], ["geliyolar"], []),
    ("gidiyon mu oraya", ["Gidiyorsun", "oraya"], ["gidiyon"], []),
    ("gidiyolar yola çıktılar", ["Gidiyorlar"], ["gidiyolar"], []),
    ("yapıyom şu anda", ["Yapıyorum"], ["yapıyom"], []),
    ("yapıyon mu işini", ["Yapıyorsun", "işini"], ["yapıyon"], []),
    ("yapıyolar yine", ["Yapıyorlar"], ["yapıyolar"], []),
    ("istiyom bunu gerçekten", ["İstiyorum", "gerçekten"], ["istiyom"], []),
    ("istemiyom gelme sakın", ["İstemiyorum", "gelme sakın"], ["istemiyom"], []),

    # --- 56-80: Texting shorthands, greetings & particles ---
    ("slm nbr", ["Selam", "ne haber"], ["slm", "nbr"], []),
    ("mrb cnm", ["Merhaba", "canım"], ["mrb", "cnm"], []),
    ("eyw kral adamsın", ["Teşekkür ederim"], ["eyw"], []),
    ("eyvallah bilader", ["Teşekkür ederim"], ["eyvallah", "bilader"], []),
    ("tşk ederim ilginize", ["Teşekkürler", "ederim"], ["tşk"], []),
    ("tskler herşey için", ["Teşekkürler", "her şey için"], ["tskler", "herşey"], []),
    ("thx bro", ["Teşekkürler"], ["thx", "bro"], []),
    ("tmm grs", ["Tamam", "görüşürüz"], ["tmm", "grs"], []),
    ("tm kib", ["Tamam", "kendine iyi bak"], ["tm", "kib"], []),
    ("ok grş sonra", ["Tamam", "görüşürüz"], ["ok", "grş"], []),
    ("bb ben kaçtım", ["Hoşça kal", "ben kaçtım"], ["bb"], []),
    ("bye görüşürüz", ["Hoşça kal", "görüşürüz"], ["bye"], []),
    ("sa hayırlı işler", ["Selamünaleyküm", "hayırlı işler"], ["sa"], []),
    ("as hoş geldin", ["Aleyküm selam", "hoş geldin"], ["as"], []),
    ("gnydn millet", ["Günaydın", "millet"], ["gnydn"], []),
    ("iyigeceler tatlı rüyalar", ["İyi geceler", "tatlı rüyalar"], ["iyigeceler"], []),
    ("ztn biliyordum böyle olacağını", ["Zaten", "biliyordum"], ["ztn"], []),
    ("hyr olmaz öyle şey", ["Hayır", "olmaz öyle şey"], ["hyr"], []),
    ("ewt haklısın", ["Evet", "haklısın"], ["ewt"], []),
    ("bnc de çok mantıklı", ["Bence", "çok mantıklı"], ["bnc"], []),
    ("sne ne bne ne", ["Sana", "ben"], ["sne", "bne"], []),
    ("snn bnm davam değil bu", ["Senin", "benim"], ["snn", "bnm"], []),
    ("bişey dicem sana", ["Bir şey", "diyeceğim"], ["bişey"], []),
    ("hicbişey anlamadım valla", ["Hiçbir şey", "doğrusu"], ["hicbişey", "valla"], []),
    ("herşey yolunda merak etme", ["Her şey", "yolunda"], ["herşey"], []),

    # --- 81-105: Shorthand locations, questions & particles ---
    ("bida yapma bunu", ["Bir daha", "yapma bunu"], ["bida"], []),
    ("bikere dinle beni", ["Bir kere", "dinle beni"], ["bikere"], []),
    ("bian öyle sandım", ["Bir an", "öyle sandım"], ["bian"], []),
    ("bigün buluşalım", ["Bir gün", "buluşalım"], ["bigün"], []),
    ("biara konuşalım", ["Bir ara", "konuşalım"], ["biara"], []),
    ("nerde kaldın ya", ["Nerede", "kaldın"], ["nerde"], []),
    ("nerden geliyorsun sen", ["Nereden", "geliyorsun"], ["nerden"], []),
    ("burda bekliyorum seni", ["Burada", "bekliyorum"], ["burda"], []),
    ("şurda oturuyoruz gel", ["Şurada", "oturuyoruz"], ["şurda"], []),
    ("içerde kimse yok", ["İçeride", "kimse yok"], ["içerde"], []),
    ("dışarda hava soğuk", ["Dışarıda", "hava soğuk"], ["dışarda"], []),
    ("yukarda bekliyorlar", ["Yukarıda", "bekliyorlar"], ["yukarda"], []),
    ("ndn öyle dedin ki", ["Neden", "öyle dedin ki"], ["ndn"], []),
    ("nie inanmıyorsun bana", ["Neden", "inanmıyorsun"], ["nie"], []),
    ("acb ne zaman gelir", ["Acaba", "ne zaman gelir"], ["acb"], []),
    ("harbi söylüyorum", ["Gerçekten", "söylüyorum"], ["harbi"], []),
    ("harbiden çok iyiydi", ["Gerçekten", "çok iyiydi"], ["harbiden"], []),
    ("ciddili mi bu", ["Ciddi olarak", "bu"], ["ciddili"], []),
    ("pki sen bilirsin", ["Peki", "sen bilirsin"], ["pki"], []),
    ("tmmdr halloldu", ["Tamamdır", "halloldu"], ["tmmdr"], []),
    ("nssn canım", ["Nasılsın", "canım"], ["nssn"], []),
    ("iydr sen nasılsın", ["İyidir", "sen nasılsın"], ["iydr"], []),
    ("skntı yok hallederim", ["Sorun yok", "hallederim"], ["skntı yok"], []),
    ("fln filan işte", ["Falan", "filan işte"], ["fln"], []),
    ("herkez burada mı", ["Herkes", "burada mı"], ["herkez"], []),

    # --- 106-130: Heavy profanity & vulgar expressions neutralized ---
    ("siktir git başımdan", ["buradan uzaklaş"], ["siktir git"], []),
    ("siktir et kafana takma", ["boş ver", "kafana takma"], ["siktir et"], []),
    ("amına koyayım böyle işin", ["böyle işin"], ["amına koyayım"], []),
    ("amk ya yine mi bozuldu", ["yine mi bozuldu"], ["amk"], []),
    ("aq çocuğu seni", ["seni"], ["aq"], []),
    ("orospu çocuğu seni rezil", ["ahlaksız kimse"], ["orospu çocuğu"], []),
    ("bok gibi olmuş burası", ["çok kötü", "olmuş burası"], ["bok gibi"], []),
    ("yarrak gibi bir gündü", ["çok kötü", "bir gündü"], ["yarrak gibi"], []),
    ("taşşak mı geçiyorsun benimle", ["alay", "geçiyorsun"], ["taşşak"], []),
    ("sikimde değil ne olduğu", ["umurumda değil"], ["sikimde değil"], []),
    ("yarrak yedin sen şimdi", ["büyük hata yaptın"], ["yarrak yedin"], []),
    ("bok yedin dinlemedin beni", ["hata yaptın"], ["bok yedin"], []),
    ("göt oldu hepsi sonunda", ["mahcup oldu"], ["göt oldu"], []),
    ("kafana sıçarım senin", ["sana çok kızarım"], ["kafana sıçarım"], []),
    ("ağzına sıçayım böyle düzenin", ["seni kınıyorum"], ["ağzına sıçayım"], []),
    ("aptal herif ne yaptın sen", ["düşüncesiz kişi"], ["aptal herif"], []),
    ("salak herif düşünemedin mi", ["düşüncesiz kişi"], ["salak herif"], []),
    ("gerizekalı herif defol", ["anlayışsız kişi"], ["gerizekalı herif"], []),
    ("sg buradan hemen", ["uzaklaş", "buradan hemen"], ["sg"], []),
    ("oç yaptığın harekete bak", ["ahlaksız kimse"], ["oç"], []),
    ("piç kurusu seni", ["saygısız kimse"], ["piç"], []),
    ("yavşak adamın tekisin", ["güvenilmez kimse"], ["yavşak"], []),
    ("puştluk yapma bana", ["kötü niyetli"], ["puştluk"], []),
    ("şerefsiz insan ne olacak", ["onursuz kimse"], ["şerefsiz"], []),
    ("namussuz adam güvenilmez", ["dürüst olmayan kimse"], ["namussuz"], []),

    # --- 131-145: Irregular & SpongeBob Casing ---
    ("sElAm nBR kAnKa", ["Selam ne haber"], ["sElAm", "nBR", "kAnKa"], []),
    ("bÖyLe yAzI mI oLuR", ["Böyle yazı mı olur"], ["bÖyLe", "yAzI", "oLuR"], []),
    ("nApIyOn oRaLaRdA", ["Ne yapıyorsun oralarda"], ["nApIyOn", "oRaLaRdA"], []),
    ("gElİyOm bEkLe bEnİ", ["Geliyorum bekle beni"], ["gElİyOm", "bEkLe"], []),
    ("kArDo nErDeSiN sEn", ["Neredesin sen"], ["kArDo", "nErDeSiN"], []),
    ("hErŞeY çOk gÜzEl oLaCaK", ["Her şey çok güzel olacak"], ["hErŞeY", "gÜzEl", "oLaCaK"], []),
    ("tAmAm aNlAdIm sEnİ", ["Tamam anladım seni"], ["tAmAm", "aNlAdIm"], []),
    ("nOlUr yArDıM eT bAnA", ["Ne olur yardım et bana"], ["nOlUr"], []),
    ("lÜtFeEn cEvAp vEr", ["Lütfen cevap ver"], ["lÜtFeEn"], []),
    ("eYw kRaL aDaMsIn", ["Teşekkür ederim"], ["eYw"], []),
    ("dÜşÜnÜyOm aMa bUlAmIyOm", ["Düşünüyorum ama bulamıyorum"], ["dÜşÜnÜyOm", "bUlAmIyOm"], []),
    ("yApAmIyOm bU iŞi", ["Yapamıyorum bu işi"], ["yApAmIyOm"], []),
    ("gİdİyOm bEn gÖrÜşÜrÜz", ["Gidiyorum ben görüşürüz"], ["gİdİyOm"], []),
    ("çAlIşIyOm şİmDİ", ["Çalışıyorum şimdi"], ["çAlIşIyOm"], []),
    ("kOnUşUyOm sEnİnLe", ["Konuşuyorum seninle"], ["kOnUşUyOm"], []),

    # --- 146-170: Combined Slang, Severe Profanity, Preserved URLs and Preserved Emojis ---
    (
        "slm nbr https://umbra.org/portal?user=admin&id=123 🔥 👍",
        ["Selam ne haber"],
        ["slm", "nbr"],
        ["https://umbra.org/portal?user=admin&id=123", "🔥", "👍"]
    ),
    (
        "kanka şu linke baksana: https://github.com/umbra/sec#readme 🚀 napıon",
        ["Ne yapıyorsun"],
        ["kanka", "napıon"],
        ["https://github.com/umbra/sec#readme", "🚀"]
    ),
    (
        "eyw reis https://t.me/anonim_bot?start=ref456 ❤️ harikaaa olmuş",
        ["Teşekkür ederim", "Harika olmuş"],
        ["eyw", "harikaaa"],
        ["https://t.me/anonim_bot?start=ref456", "❤️"]
    ),
    (
        "geliyom hemen https://maps.google.com/loc?lat=41.0&lng=29.0 👀 bekle",
        ["Geliyorum hemen", "bekle"],
        ["geliyom"],
        ["https://maps.google.com/loc?lat=41.0&lng=29.0", "👀"]
    ),
    (
        "napcan bu linkle https://umbra-defense.net/verify?token=XYZ_999 🛡️",
        ["Ne yapacaksın"],
        ["napcan"],
        ["https://umbra-defense.net/verify?token=XYZ_999", "🛡️"]
    ),
    (
        "bida buraya atma www.umbra-network.org/gateway ⚡ anladın mı",
        ["Bir daha buraya atma", "anladın mı"],
        ["bida"],
        ["www.umbra-network.org/gateway", "⚡"]
    ),
    (
        "siktir et şu sayfayı https://news.example.com/item/101?track=false 😎 boşver",
        ["boş ver"],
        ["siktir et"],
        ["https://news.example.com/item/101?track=false", "😎"]
    ),
    (
        "ayyyyynen öyle https://umbra.org/whitepaper.pdf 🇹🇷 çok haklısın",
        ["Aynen öyle", "çok haklısın"],
        ["ayyyyynen"],
        ["https://umbra.org/whitepaper.pdf", "🇹🇷"]
    ),
    (
        "mrb https://chat.umbra.io/sa/bi/tm?code=1234 💪 nasılsın",
        ["Merhaba", "nasılsın"],
        ["mrb"],
        ["https://chat.umbra.io/sa/bi/tm?code=1234", "💪"]
    ),
    (
        "tmm hallederiz https://anon.is/file/abc-def?dl=1 🚀 skntı yok",
        ["Tamam hallederiz", "sorun yok"],
        ["tmm", "skntı yok"],
        ["https://anon.is/file/abc-def?dl=1", "🚀"]
    ),
    (
        "nolurrrr şuraya tıkla: https://service.org/login?redir=/home ⚠️ acil",
        ["Ne olur", "acil"],
        ["nolurrrr"],
        ["https://service.org/login?redir=/home", "⚠️"]
    ),
    (
        "herşey hazır https://dashboard.umbra.io/metrics?time=now 🔥 süpeeeer",
        ["Her şey hazır", "Süper"],
        ["herşey", "süpeeeer"],
        ["https://dashboard.umbra.io/metrics?time=now", "🔥"]
    ),
    (
        "napıonuz https://api.umbra.org/v1/status?check=full 🛡️ herkez toplansın",
        ["Ne yapıyorsunuz", "herkes toplansın"],
        ["napıonuz", "herkez"],
        ["https://api.umbra.org/v1/status?check=full", "🛡️"]
    ),
    (
        "sElAm nBR https://example.com/invite?ref=TEST&val=999 👍",
        ["Selam ne haber"],
        ["sElAm", "nBR"],
        ["https://example.com/invite?ref=TEST&val=999", "👍"]
    ),
    (
        "harbi mi diyosun https://umbra.org/doc/sec_guide.html ❤️ inanamıyorum",
        ["Gerçekten", "inanamıyorum"],
        ["harbi"],
        ["https://umbra.org/doc/sec_guide.html", "❤️"]
    ),
    (
        "sknti yok bro https://umbra.org/help?q=anonimlik 😊 hallederiz",
        ["Sorun yok", "hallederiz"],
        ["sknti yok", "bro"],
        ["https://umbra.org/help?q=anonimlik", "😊"]
    ),
    (
        "napiyosun orda https://umbra.org/forum/thread/77?page=2 👀 gel buraya",
        ["Ne yapıyorsun", "gel buraya"],
        ["napiyosun"],
        ["https://umbra.org/forum/thread/77?page=2", "👀"]
    ),
    (
        "yapcam bu işi https://github.com/umbra/tooling?branch=main 🚀 gör bak",
        ["Yapacağım", "gör bak"],
        ["yapcam"],
        ["https://github.com/umbra/tooling?branch=main", "🚀"]
    ),
    (
        "gidiyom ben https://umbra.org/logout?session=987654 👋 bay bay",
        ["Gidiyorum ben", "hoşça kal"],
        ["gidiyom", "bay bay"],
        ["https://umbra.org/logout?session=987654", "👋"]
    ),
    (
        "bişey sorcam https://wiki.umbra.org/faq#section-2 ❓ bakar mısın",
        ["Bir şey", "bakar mısın"],
        ["bişey"],
        ["https://wiki.umbra.org/faq#section-2", "❓"]
    ),
    (
        "eyvallah hocam https://umbra.org/download/client_v2.zip 💾 tşkler",
        ["Teşekkür ederim", "teşekkürler"],
        ["eyvallah", "tşkler"],
        ["https://umbra.org/download/client_v2.zip", "💾"]
    ),
    (
        "nolcak halimiz https://crypto.umbra.org/tx/0xabc123?block=456 📉 bakalım",
        ["Ne olacak halimiz", "bakalım"],
        ["nolcak"],
        ["https://crypto.umbra.org/tx/0xabc123?block=456", "📉"]
    ),
    (
        "napıom ben burda https://umbra.org/terminal?user=root&debug=1 💻 kafam karıştı",
        ["Ne yapıyorum", "kafam karıştı"],
        ["napıom"],
        ["https://umbra.org/terminal?user=root&debug=1", "💻"]
    ),
    (
        "TAMAMI BÜYÜK YAZILMIŞ METİN VE LİNK https://umbra.org/loud?volume=max 🔥",
        ["Tamamı büyük yazılmış metin"],
        [],
        ["https://umbra.org/loud?volume=max", "🔥"]
    ),
    (
        "ciddili söylüyorum https://umbra.org/status?live=1 👍 skntı yok",
        ["Ciddi olarak", "sorun yok"],
        ["ciddili", "skntı yok"],
        ["https://umbra.org/status?live=1", "👍"]
    ),
]


class TestLinguisticNeutralizationStress:
    """Stress tests verifying Turkish neutralization across 165+ realistic inputs."""

    def test_dataset_size_requirement(self):
        """Verifies requirement of at least 150+ inputs."""
        assert len(STRESS_LINGUISTIC_DATASET) >= 150, (
            f"Dataset size must be 150+, got {len(STRESS_LINGUISTIC_DATASET)}"
        )

    @pytest.mark.parametrize("raw_input,expected_sub,forbidden_sub,preserved_entities", STRESS_LINGUISTIC_DATASET)
    def test_single_neutralization_case(self, raw_input, expected_sub, forbidden_sub, preserved_entities):
        cleaned = TextNeutralizer.neutralize(raw_input)

        # 1. Output must not be empty
        assert cleaned and len(cleaned.strip()) > 0

        # 2. Turkish character integrity: UTF-8 encoding valid and no mojibake
        encoded = cleaned.encode("utf-8")
        assert encoded.decode("utf-8") == cleaned
        mojibake_markers = ["Ã§", "ÄŸ", "ÅŸ", "Ã¼", "Ã¶", "Ä±", "Ã‡", "Äž", "Åž", "Ãœ", "Ã–", "Ä°"]
        for marker in mojibake_markers:
            assert marker not in cleaned, f"Mojibake detected: {marker} in '{cleaned}'"

        # 3. Expected standard Turkish words must be present
        for exp in expected_sub:
            assert exp.lower() in cleaned.lower(), (
                f"Expected standard form '{exp}' missing from output: '{cleaned}' (raw: '{raw_input}')"
            )

        # 4. Forbidden slang / vulgar / elongated terms must NOT be present
        for forb in forbidden_sub:
            if any(c.isupper() for c in forb[1:]):
                assert forb not in cleaned, (
                    f"Irregular casing token '{forb}' was NOT normalized in output: '{cleaned}'"
                )
            else:
                pattern = rf"(?<!\w){re.escape(forb)}(?!\w)"
                assert not re.search(pattern, cleaned, re.IGNORECASE), (
                    f"Forbidden token '{forb}' was NOT neutralized in output: '{cleaned}' (raw: '{raw_input}')"
                )

        # 5. URLs and emojis must be preserved exactly
        for entity in preserved_entities:
            assert entity in cleaned, (
                f"Preserved entity '{entity}' was altered or stripped in output: '{cleaned}'"
            )

    def test_extreme_elongations_reduction(self):
        """Tests extreme character elongations (20+ repeated letters)."""
        input_text = "ayyyyyyyyyyyyyyyyyyyyynen reiiiiiiiiiiiiiiiiiiissssssssss lüüütfeeeeeeeeeeeeeeeeeen"
        cleaned = TextNeutralizer.neutralize(input_text)
        assert "Aynen" in cleaned
        assert "lütfen" in cleaned.lower()
        assert "ayyyyy" not in cleaned
        assert "lüüü" not in cleaned

    def test_multiple_urls_in_single_message_preservation(self):
        """Tests that multiple distinct URLs in one message remain intact and separate."""
        raw = (
            "kanka link bir: https://site1.org/sa/bi?id=1 "
            "link iki: http://site2.com/test#anchor "
            "link üç: https://sub.site3.io:8080/path/to/doc?query=OK&ref=TR 🔥 🚀"
        )
        res = TextNeutralizer.neutralize(raw)
        assert "https://site1.org/sa/bi?id=1" in res
        assert "http://site2.com/test#anchor" in res
        assert "https://sub.site3.io:8080/path/to/doc?query=OK&ref=TR" in res
        assert "🔥" in res and "🚀" in res
        assert "kanka" not in res.lower()

    def test_profanity_modes(self):
        """Tests 'mask', 'remove', and 'neutralize' profanity sanitization modes."""
        raw = "Bu herif tam bir yavşak ve şerefsiz"

        # 1. Neutralize mode
        clean_neutral = TextNeutralizer(profanity_mode="neutralize").neutralize(raw)
        assert "güvenilmez kimse" in clean_neutral
        assert "onursuz kimse" in clean_neutral

        # 2. Mask mode
        clean_masked = TextNeutralizer(profanity_mode="mask").neutralize(raw)
        assert "y****k" in clean_masked
        assert "ş******z" in clean_masked

        # 3. Remove mode
        clean_removed = TextNeutralizer(profanity_mode="remove").neutralize(raw)
        assert "yavşak" not in clean_removed and "şerefsiz" not in clean_removed


# ===========================================================================
# 2. Database Concurrency Stress Suite (100 Threads)
# ===========================================================================

class TestDatabaseConcurrencyStress:
    """Tests SQLite concurrency under 100 simultaneous threads without lockouts."""

    def test_100_concurrent_threads_crud_stress(self):
        """Spawns 100 concurrent threads performing write, read, update, delete operations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "stress_concurrency.db")
            db = DatabaseManager(db_path=db_path)

            bot_id = db.add_bot(token="STRESS_BOT_TOKEN_100", name="ConcurrencyBot", username="concurrency_bot")
            chat = db.get_or_create_chat(bot_id=bot_id, chat_id=99999, sender_name="StressTester", username="tester")
            chat_id = chat["chat_id"]

            errors: List[str] = []
            created_message_ids: List[int] = []
            lock = threading.Lock()

            def worker_task(thread_id: int):
                try:
                    # 1. Insert message
                    msg_id = db.save_message(
                        bot_id=bot_id,
                        chat_id=chat_id,
                        message_id=10000 + thread_id,
                        is_outgoing=thread_id % 2,
                        text=f"Stress message from thread {thread_id}",
                        media_type="photo" if thread_id % 5 == 0 else None,
                        media_path=f"/tmp/photo_{thread_id}.jpg" if thread_id % 5 == 0 else None
                    )
                    with lock:
                        created_message_ids.append(msg_id)

                    # 2. Read operations
                    msg = db.get_message(msg_id)
                    assert msg is not None, f"Message {msg_id} not found immediately after write"
                    assert msg["text"] == f"Stress message from thread {thread_id}"

                    msgs = db.get_messages(bot_id=bot_id, chat_id=chat_id)
                    assert len(msgs) > 0

                    # 3. Update text & reactions
                    db.update_message_text(msg_id, f"Updated message {thread_id} - PASS")
                    db.update_message_reaction(msg_id, "👍")
                    db.set_chat_note(bot_id, chat_id, f"Note from thread {thread_id}")

                    # 4. Settings write & read
                    db.set_setting(f"stress_setting_{thread_id}", f"val_{thread_id}")
                    val = db.get_setting(f"stress_setting_{thread_id}")
                    assert val == f"val_{thread_id}"

                    # 5. Delete operation for even-numbered threads
                    if thread_id % 2 == 0:
                        db.mark_message_deleted_locally(msg_id)

                except Exception as exc:
                    with lock:
                        errors.append(f"Thread-{thread_id} failed: {type(exc).__name__}: {exc}")

            # Launch 100 threads concurrently
            threads = [threading.Thread(target=worker_task, args=(i,), name=f"StressThread-{i}") for i in range(100)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30.0)

            # Assertions
            assert len(errors) == 0, f"Database concurrency stress encountered errors:\n" + "\n".join(errors)
            assert len(created_message_ids) == 100, f"Expected 100 created messages, got {len(created_message_ids)}"

            # Verify persistent state integrity
            all_db_msgs = db.get_messages(bot_id=bot_id, chat_id=chat_id)
            # 50 messages were locally deleted, 50 remain active
            assert len(all_db_msgs) == 50, f"Expected 50 non-deleted messages, got {len(all_db_msgs)}"

    def test_concurrent_chat_mutations_and_bot_operations(self):
        """Simulates 50 threads concurrently updating chat states and bot profiles."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "stress_chats.db")
            db = DatabaseManager(db_path=db_path)
            bot_id = db.add_bot(token="BOT_MUTATION", name="MutationBot", username="mutation_bot")

            # Pre-create 10 chats
            for c_id in range(1, 11):
                db.get_or_create_chat(bot_id, c_id, f"User {c_id}", f"user_{c_id}")

            errors: List[str] = []

            def mutator_task(idx: int):
                try:
                    target_chat = (idx % 10) + 1
                    db.toggle_pin_chat(bot_id, target_chat, idx % 2)
                    db.toggle_block_chat(bot_id, target_chat, 0)
                    db.update_chat_profile(
                        bot_id=bot_id,
                        chat_id=target_chat,
                        bio=f"Bio update by thread {idx}",
                        custom_note=f"Note {idx}"
                    )
                    chats = db.get_chats_for_bot(bot_id)
                    assert len(chats) == 10
                except Exception as exc:
                    errors.append(f"Mutator-{idx} error: {exc}")

            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(mutator_task, i) for i in range(50)]
                for f in as_completed(futures):
                    f.result()

            assert len(errors) == 0


# ===========================================================================
# 3. Spam & Flood Protection Stress Suite (High Frequency & Albums)
# ===========================================================================

class TestSpamAndFloodProtectionStress:
    """Tests SpamProtector under high frequency message bombardment and album uploads."""

    def test_high_frequency_message_bombardment_50_msgs_per_sec(self, monkeypatch):
        """Simulates 50 messages/sec flood and verifies graduated penalty (cooldown -> permanent ban)."""
        current_time = 1000.0

        def mock_time():
            return current_time

        monkeypatch.setattr(time, "time", mock_time)

        # Threshold: 12 messages in 5s
        sp = SpamProtector(max_messages=12, window_seconds=5.0, enabled=True)
        bot_id, chat_id = 1, 5555

        # 1. Send 12 messages rapidly within 0.24 seconds (50 msgs/s pace: 0.02s per msg)
        for i in range(12):
            current_time += 0.02
            is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text=f"Flood msg {i}")
            assert is_spam is False, f"Message {i} unexpectedly blocked: {reason}"
            assert is_perm is False

        # 2. 13th message exceeds max_messages (12) -> triggers 1st violation (45s temporary cooldown)
        current_time += 0.02
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text="Flood msg 12")
        assert is_spam is True
        assert is_perm is False
        assert "Geçici 45 sn mola" in reason

        # 3. Messages 14 to 50 arrive during active cooldown -> all blocked with cooldown notice
        for i in range(13, 50):
            current_time += 0.02
            is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text=f"Flood msg {i}")
            assert is_spam is True
            assert is_perm is False
            assert "Kullanıcı geçici molada" in reason

        # 4. Advance time past the 45-second temporary cooldown
        current_time += 46.0

        # 5. First message after cooldown expires is permitted
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text="Post-cooldown message")
        assert is_spam is False
        assert is_perm is False

        # 6. User resumes high-frequency flooding after expiry -> triggers 2nd violation -> PERMANENT BLOCK
        for i in range(12):
            current_time += 0.02
            sp.check_incoming(bot_id, chat_id, text=f"Second flood {i}")

        current_time += 0.02
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, text="Second flood triggering ban")
        assert is_spam is True
        assert is_perm is True
        assert "kalıcı engellendi" in reason

    def test_telegram_album_burst_upload_stress(self, monkeypatch):
        """Simulates 20-photo album burst upload and verifies it does NOT get banned as flood."""
        current_time = 2000.0

        def mock_time():
            return current_time

        monkeypatch.setattr(time, "time", mock_time)

        # max_messages=12, max_media=10
        sp = SpamProtector(max_messages=12, window_seconds=5.0, max_media=10, media_window_seconds=8.0, enabled=True)
        bot_id, chat_id = 1, 7777

        # Send a 20-photo album with identical media_group_id within 0.4 seconds
        album_id = "telegram_album_stress_99999"
        for photo_idx in range(20):
            current_time += 0.02
            is_spam, is_perm, reason = sp.check_incoming(
                bot_id=bot_id,
                chat_id=chat_id,
                is_media=True,
                media_group_id=album_id
            )
            assert is_spam is False, f"Album photo {photo_idx} was falsely flagged: {reason}"
            assert is_perm is False

        # Now send separate non-album media files to test that genuine media flood is still caught
        # max_media = 10. Album counts as 1. So 9 more media files allowed.
        for i in range(9):
            current_time += 0.1
            is_spam, _, _ = sp.check_incoming(bot_id, chat_id, is_media=True, media_group_id=None)
            assert is_spam is False, f"Standalone media {i} unexpectedly blocked"

        # The 10th standalone media exceeds max_media (1 + 10 = 11 > 10) -> triggers violation!
        current_time += 0.1
        is_spam, is_perm, reason = sp.check_incoming(bot_id, chat_id, is_media=True, media_group_id=None)
        assert is_spam is True
        assert is_perm is False
        assert "Hızlı dosya/medya gönderimi" in reason

    def test_50_concurrent_threads_spam_protector_isolation(self):
        """Simulates 50 concurrent threads checking spam across 25 distinct chats."""
        sp = SpamProtector(max_messages=10, window_seconds=3.0, enabled=True)
        errors = []

        def spammer_task(thread_id: int):
            try:
                # 25 chats, 2 threads per chat
                chat_id = (thread_id % 25) + 1000
                for msg_idx in range(5):
                    is_spam, _, _ = sp.check_incoming(
                        bot_id=1,
                        chat_id=chat_id,
                        text=f"Concurrent msg {msg_idx} from {thread_id}"
                    )
            except Exception as e:
                errors.append(f"Thread {thread_id} failed: {e}")

        threads = [threading.Thread(target=spammer_task, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(errors) == 0
