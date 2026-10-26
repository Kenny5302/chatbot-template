"""All customer-facing interface text, in one place.

TO EDIT OR REVIEW A TRANSLATION: change the text below. Nothing else needs to change.
  - Every language must have every key (a test checks this).
  - Keep the {placeholders} exactly as they are: {name} is the business name, {phone} its phone number,
    {max} the message length limit.
  - "greeting" must say that this is a virtual assistant and an AI, not a person (California bot disclosure).
"""

from app.businesses import Business

SUPPORTED = ("en", "es", "pa")

# What the language buttons say. Each is written in its own language so people can find theirs.
BUTTON_LABELS = {"en": "English", "es": "Español", "pa": "ਪੰਜਾਬੀ"}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "greeting": (
            "Hi! I'm {name}'s virtual assistant, an AI and not a person. I can answer questions about our "
            "hours, services, and pricing, or take your details so our team can call you back. How can I help?"
        ),
        "privacy": "Chats are saved so the shop can follow up with you.",
        "subtitle": "Virtual assistant (AI)",
        "chat_with": "Chat with {name}",
        "placeholder": "Type your message...",
        "message_label": "Message",
        "send": "Send",
        "call": "Call",
        "close": "Close chat",
        "language_label": "Language",
        "error_network": "Can't reach the assistant right now. Please call us at {phone}.",
        "error_rate_limit": "You're sending messages quickly. Please wait a moment, or call us at {phone}.",
        "error_invalid": "Please send a message between 1 and {max} characters.",
        "error_generic": "Something went wrong. Please try again, or call us at {phone}.",
        "reply_fallback": "Sorry, I'm having trouble right now. Please call us at {phone} and we'll be glad to help.",
        "reply_turn_limit": "We've been chatting for a while, so let me connect you with the team. Please call us at {phone}.",
        "reply_daily_limit": "We're getting a lot of messages today and can't chat right now. Please call us at {phone} and we'll be glad to help.",
        "crisis_line": "If you're thinking about hurting yourself, please call or text 988 (Suicide & Crisis Lifeline) any time, or call 911 if you're in immediate danger.",
        "reply_off_topic": "I can only help with questions about {name}. Can I help with our services, hours, or a callback?",
    },
    "es": {
        "greeting": (
            "¡Hola! Soy el asistente virtual de {name}, una inteligencia artificial y no una persona. Puedo "
            "responder preguntas sobre horarios, servicios y precios, o tomar sus datos para que nuestro equipo "
            "le devuelva la llamada. ¿En qué puedo ayudarle?"
        ),
        "privacy": "Guardamos los chats para que el negocio pueda darle seguimiento.",
        "subtitle": "Asistente virtual (IA)",
        "chat_with": "Chatear con {name}",
        "placeholder": "Escriba su mensaje...",
        "message_label": "Mensaje",
        "send": "Enviar",
        "call": "Llamar",
        "close": "Cerrar chat",
        "language_label": "Idioma",
        "error_network": "No podemos conectar con el asistente en este momento. Por favor llámenos al {phone}.",
        "error_rate_limit": "Está enviando mensajes muy rápido. Espere un momento o llámenos al {phone}.",
        "error_invalid": "Envíe un mensaje de entre 1 y {max} caracteres.",
        "error_generic": "Algo salió mal. Inténtelo de nuevo o llámenos al {phone}.",
        "reply_fallback": "Lo siento, tengo problemas en este momento. Llámenos al {phone} y con gusto le ayudaremos.",
        "reply_turn_limit": "Hemos conversado un buen rato, así que le paso con el equipo. Por favor llámenos al {phone}.",
        "reply_daily_limit": "Hoy hemos recibido muchos mensajes y no podemos chatear en este momento. Por favor llámenos al {phone} y con gusto le ayudaremos.",
        "crisis_line": "Si está pensando en hacerse daño, por favor llame o envíe un mensaje de texto al 988 (Línea de Prevención del Suicidio y Crisis) en cualquier momento, o llame al 911 si está en peligro inmediato.",
        "reply_off_topic": "Solo puedo ayudar con preguntas sobre {name}. ¿Puedo ayudarle con nuestros servicios, horarios o una llamada de vuelta?",
    },
    "pa": {
        "greeting": (
            "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ {name} ਦਾ ਵਰਚੁਅਲ ਅਸਿਸਟੈਂਟ ਹਾਂ, ਇੱਕ AI, ਕੋਈ ਇਨਸਾਨ ਨਹੀਂ। ਮੈਂ ਸਾਡੇ ਸਮੇਂ, ਸੇਵਾਵਾਂ ਅਤੇ "
            "ਕੀਮਤਾਂ ਬਾਰੇ ਸਵਾਲਾਂ ਦੇ ਜਵਾਬ ਦੇ ਸਕਦਾ ਹਾਂ, ਜਾਂ ਤੁਹਾਡੀ ਜਾਣਕਾਰੀ ਲੈ ਸਕਦਾ ਹਾਂ ਤਾਂ ਜੋ ਸਾਡੀ ਟੀਮ ਤੁਹਾਨੂੰ ਵਾਪਸ "
            "ਫ਼ੋਨ ਕਰ ਸਕੇ। ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?"
        ),
        "privacy": "ਚੈਟ ਸੰਭਾਲੀ ਜਾਂਦੀ ਹੈ ਤਾਂ ਜੋ ਦੁਕਾਨ ਤੁਹਾਡੇ ਨਾਲ ਦੁਬਾਰਾ ਸੰਪਰਕ ਕਰ ਸਕੇ।",
        "subtitle": "ਵਰਚੁਅਲ ਅਸਿਸਟੈਂਟ (AI)",
        "chat_with": "{name} ਨਾਲ ਚੈਟ ਕਰੋ",
        "placeholder": "ਆਪਣਾ ਸੁਨੇਹਾ ਲਿਖੋ...",
        "message_label": "ਸੁਨੇਹਾ",
        "send": "ਭੇਜੋ",
        "call": "ਕਾਲ ਕਰੋ",
        "close": "ਚੈਟ ਬੰਦ ਕਰੋ",
        "language_label": "ਭਾਸ਼ਾ",
        "error_network": "ਇਸ ਵੇਲੇ ਅਸਿਸਟੈਂਟ ਨਾਲ ਸੰਪਰਕ ਨਹੀਂ ਹੋ ਰਿਹਾ। ਕਿਰਪਾ ਕਰਕੇ ਸਾਨੂੰ {phone} 'ਤੇ ਕਾਲ ਕਰੋ।",
        "error_rate_limit": "ਤੁਸੀਂ ਬਹੁਤ ਤੇਜ਼ੀ ਨਾਲ ਸੁਨੇਹੇ ਭੇਜ ਰਹੇ ਹੋ। ਕਿਰਪਾ ਕਰਕੇ ਥੋੜ੍ਹਾ ਰੁਕੋ ਜਾਂ ਸਾਨੂੰ {phone} 'ਤੇ ਕਾਲ ਕਰੋ।",
        "error_invalid": "ਕਿਰਪਾ ਕਰਕੇ 1 ਤੋਂ {max} ਅੱਖਰਾਂ ਦਾ ਸੁਨੇਹਾ ਭੇਜੋ।",
        "error_generic": "ਕੁਝ ਗਲਤ ਹੋ ਗਿਆ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ ਜਾਂ ਸਾਨੂੰ {phone} 'ਤੇ ਕਾਲ ਕਰੋ।",
        "reply_fallback": "ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਇਸ ਵੇਲੇ ਮੁਸ਼ਕਲ ਆ ਰਹੀ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਸਾਨੂੰ {phone} 'ਤੇ ਕਾਲ ਕਰੋ, ਅਸੀਂ ਖੁਸ਼ੀ ਨਾਲ ਮਦਦ ਕਰਾਂਗੇ।",
        "reply_turn_limit": "ਅਸੀਂ ਕਾਫ਼ੀ ਦੇਰ ਗੱਲ ਕਰ ਲਈ ਹੈ, ਇਸ ਲਈ ਤੁਹਾਨੂੰ ਸਾਡੀ ਟੀਮ ਨਾਲ ਜੋੜਦਾ ਹਾਂ। ਕਿਰਪਾ ਕਰਕੇ ਸਾਨੂੰ {phone} 'ਤੇ ਕਾਲ ਕਰੋ।",
        "reply_daily_limit": "ਅੱਜ ਸਾਨੂੰ ਬਹੁਤ ਸਾਰੇ ਸੁਨੇਹੇ ਮਿਲੇ ਹਨ ਅਤੇ ਅਸੀਂ ਇਸ ਵੇਲੇ ਚੈਟ ਨਹੀਂ ਕਰ ਸਕਦੇ। ਕਿਰਪਾ ਕਰਕੇ ਸਾਨੂੰ {phone} 'ਤੇ ਕਾਲ ਕਰੋ, ਅਸੀਂ ਖੁਸ਼ੀ ਨਾਲ ਮਦਦ ਕਰਾਂਗੇ।",
        "crisis_line": "ਜੇ ਤੁਸੀਂ ਆਪਣੇ ਆਪ ਨੂੰ ਨੁਕਸਾਨ ਪਹੁੰਚਾਉਣ ਬਾਰੇ ਸੋਚ ਰਹੇ ਹੋ, ਤਾਂ ਕਿਰਪਾ ਕਰਕੇ ਕਿਸੇ ਵੀ ਸਮੇਂ 988 (ਸੁਸਾਈਡ ਐਂਡ ਕ੍ਰਾਈਸਿਸ ਲਾਈਫਲਾਈਨ) 'ਤੇ ਕਾਲ ਜਾਂ ਟੈਕਸਟ ਕਰੋ, ਜਾਂ ਜੇ ਤੁਸੀਂ ਤੁਰੰਤ ਖ਼ਤਰੇ ਵਿੱਚ ਹੋ ਤਾਂ 911 'ਤੇ ਕਾਲ ਕਰੋ।",
        "reply_off_topic": "ਮੈਂ ਸਿਰਫ਼ {name} ਬਾਰੇ ਸਵਾਲਾਂ ਵਿੱਚ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ। ਕੀ ਮੈਂ ਸਾਡੀਆਂ ਸੇਵਾਵਾਂ, ਸਮੇਂ ਜਾਂ ਵਾਪਸੀ ਕਾਲ ਬਾਰੇ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
    },
}

DEFAULT_MAX_CHARS = 1000


def text(lang: str, key: str, business: Business, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """One interface string, filled in for this business. Unknown language falls back to English."""
    template = STRINGS.get(lang, STRINGS["en"])[key]
    if key == "greeting" and lang == "en" and business.greeting:
        return business.greeting  # a business may replace the English greeting in its YAML file
    return template.format(name=business.name, phone=business.phone, max=max_chars)


def ui_for(business: Business, max_chars: int = DEFAULT_MAX_CHARS) -> dict:
    """What the chat page needs: the business's languages, in YAML order, with every string filled in."""
    order = list(dict.fromkeys(business.languages))
    return {
        "order": order,
        "labels": {code: BUTTON_LABELS[code] for code in order},
        "strings": {code: {key: text(code, key, business, max_chars) for key in STRINGS[code]} for code in order},
    }


def fallback_language(business: Business) -> str:
    return "en" if "en" in business.languages else business.languages[0]


def pick_language(business: Business, requested: str | None) -> str:
    """The language to use for a request: what the customer chose if this business supports it."""
    return requested if requested in business.languages else fallback_language(business)


def default_language(business: Business, accept_language: str) -> str:
    """First language in the browser's Accept-Language list (best first) that the business supports."""
    prefs: list[tuple[float, int, str]] = []
    for index, part in enumerate(accept_language.split(",")):
        tag, _, q = part.strip().partition(";q=")
        try:
            weight = float(q) if q else 1.0
        except ValueError:
            weight = 0.0
        primary = tag.strip().lower().split("-")[0]
        if primary and weight > 0:
            prefs.append((weight, index, primary))
    for _, _, primary in sorted(prefs, key=lambda p: (-p[0], p[1])):
        if primary in business.languages:
            return primary
    return fallback_language(business)
