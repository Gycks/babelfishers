from babelfishers.models.culture import Culture
from babelfishers.models.engine import Engine


SUPPORTED_CULTURES: dict[str, Culture] = {
    lang.code: lang
    for lang in [
        Culture(code="ar", name="Arabic"),
        Culture(code="bg", name="Bulgarian"),
        Culture(code="cs", name="Czech"),
        Culture(code="da", name="Danish"),
        Culture(code="de", name="German"),
        Culture(code="el", name="Greek"),
        Culture(code="en", name="English"),
        Culture(code="es", name="Spanish"),
        Culture(code="fi", name="Finnish"),
        Culture(code="fr", name="French"),
        Culture(code="hu", name="Hungarian"),
        Culture(code="id", name="Indonesian"),
        Culture(code="it", name="Italian"),
        Culture(code="ja", name="Japanese"),
        Culture(code="ko", name="Korean"),
        Culture(code="no", name="Norwegian", provider_codes={Engine.DeepL: "NB", Engine.Azure: "nb"}),
        Culture(code="nl", name="Dutch"),
        Culture(code="pl", name="Polish"),
        Culture(code="pt", name="Portuguese", provider_codes={Engine.DeepL: "PT-PT"}),
        Culture(code="ro", name="Romanian"),
        Culture(code="ru", name="Russian"),
        Culture(code="sk", name="Slovak"),
        Culture(code="sv", name="Swedish"),
        Culture(code="tr", name="Turkish"),
        Culture(code="uk", name="Ukrainian"),
        Culture(code="vi", name="Vietnamese"),
        Culture(code="zh", name="Chinese", provider_codes={Engine.Azure: "zh-Hans"}),
    ]
}
