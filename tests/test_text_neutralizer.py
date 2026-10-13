import pytest
from text_neutralizer import TextNeutralizer


class TestTextNeutralizer:
    def test_elongated_characters(self):
        res = TextNeutralizer.clean_elongated_characters("Lütfeeeen bana yardıııım et!")
        assert "Lütfen" in res
        assert "yardım" in res

    def test_punctuation_normalization(self):
        res = TextNeutralizer.normalize_punctuation("Nasılsın??? Gerçekten mi!!!!")
        assert "Nasılsın?" in res
        assert "Gerçekten mi!" in res

    def test_shorthand_sanitization(self):
        res = TextNeutralizer.sanitize_profanity_and_slang("slm nbr tmm bişey yapcam")
        assert "selam" in res
        assert "ne haber" in res
        assert "tamam" in res
        assert "bir şey" in res
        assert "yapacağım" in res

    def test_street_vocative_removal(self):
        res = TextNeutralizer.remove_street_vocatives("Kanka nasılsın iyi misin?")
        assert "Kanka" not in res
        assert "nasılsın" in res

        res2 = TextNeutralizer.remove_street_vocatives("Hemen buraya gel lan!")
        assert "lan" not in res2

    def test_profanity_neutralization(self):
        res = TextNeutralizer.sanitize_profanity_and_slang("Bu herif tam bir şerefsiz ve gerizekalı")
        assert "şerefsiz" not in res
        assert "gerizekalı" not in res
        assert "onursuz" in res or "anlayışsız" in res

    def test_casing_normalization(self):
        res = TextNeutralizer.normalize_sentence_casing("bÖyLe yAzI OlMaZ")
        assert "Böyle yazı olmaz" in res

        res2 = TextNeutralizer.normalize_sentence_casing("TAMAMI BÜYÜK BAĞIRAN METİN")
        assert "Tamamı büyük bağıran metin" in res2

    def test_full_pipeline_neutralize(self):
        raw = "Kanka lütfeeeen bişey söyler misin ya??? slm nbr bu arada!!"
        cleaned = TextNeutralizer.neutralize(raw)
        # Should be properly capitalized, elongated letters removed, vocatives stripped
        assert "Lütfen" in cleaned
        assert "bir şey" in cleaned
        assert "ne haber" in cleaned
        assert "???" not in cleaned
        assert "!!" not in cleaned
