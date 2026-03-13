from django.conf import settings

try:
    import google.generativeai as genai
except ImportError:
    genai = None


def _get_model():
    if genai is None:
        raise RuntimeError(
            "Gemini AI dependency is missing. Install the 'google-generativeai' package."
        )

    api_key = getattr(settings, "GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash").strip()
    if not model_name:
        model_name = "gemini-2.5-flash"

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


def ask_gemini(prompt):
    model = _get_model()
    response = model.generate_content(prompt)
    return response.text
