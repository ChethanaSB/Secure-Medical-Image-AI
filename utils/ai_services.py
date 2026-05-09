"""
ai_services.py - External AI API integrations.

Functions:
  analyze_with_huggingface(image_bytes, image_type)
      → POST raw bytes to HuggingFace Inference API
      → Returns {"label", "confidence", "all_predictions"}

  generate_clinical_report(label, confidence, image_type)
      → Sends structured prompt to Groq API (Llama 3.3 70B)
      → Returns the clinical report as a plain string

Configuration (via environment variables):
  HF_API_KEY      — HuggingFace API token (required)
  HF_MODEL_ID     — HuggingFace model to use for inference
  GROQ_API_KEY    — Groq API key (required)
  GROQ_MODEL      — Groq model name (default: llama-3.3-70b-versatile)
  HF_TIMEOUT_S    — Seconds before HTTP request times out (default: 40)
"""

import os
import logging

import requests
from groq import Groq

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_HF_API_BASE = "https://router.huggingface.co/hf-inference/models"
_DEFAULT_HF_MODEL = (
    "google/vit-base-patch16-224"
)
_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# HuggingFace — chest X-ray image classification
# ---------------------------------------------------------------------------

def analyze_with_huggingface(image_bytes: bytes, image_type: str) -> dict:
    """
    Submit raw image bytes to the HuggingFace Inference API for image
    classification (chest X-ray model by default).

    Args:
        image_bytes: Decrypted raw bytes of the image file.
        image_type : File extension — 'jpg', 'jpeg', 'png', or 'dcm'.

    Returns:
        {
          "label"           : str   — top predicted class label,
          "confidence"      : float — score 0.0–1.0,
          "all_predictions" : list  — full ranked list from HuggingFace,
          "model_used"      : str   — model ID that ran the inference,
        }

    Raises:
        ValueError   — missing HF_API_KEY.
        RuntimeError — HuggingFace API returned a non-200 status.
    """
    hf_api_key = os.getenv("HF_API_KEY", "")
    if not hf_api_key:
        raise ValueError(
            "HF_API_KEY environment variable is not set. "
            "Get a free token at https://huggingface.co/settings/tokens"
        )

    model_id = os.getenv("HF_MODEL_ID", _DEFAULT_HF_MODEL)
    url = f"{_HF_API_BASE}/{model_id}"
    timeout = int(os.getenv("HF_TIMEOUT_S", 40))

    # DICOM files are raw medical format — most HF models expect JPEG/PNG.
    if image_type == "dcm":
        logger.warning(
            "Sending a DICOM file to HuggingFace. Most standard image "
            "classification models expect JPEG/PNG. Consider using a "
            "DICOM-native model or pre-converting to PNG."
        )

    headers = {
        "Authorization": f"Bearer {hf_api_key}",
        "Content-Type": "application/octet-stream",
    }

    try:
        response = requests.post(
            url, headers=headers, data=image_bytes, timeout=timeout
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"HuggingFace request timed out after {timeout}s. "
            "The model may be cold-starting — retry in 20–30 seconds."
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"HuggingFace network error: {exc}") from exc

    # 503 means the model is warming up
    if response.status_code == 503:
        est = response.json().get("estimated_time", "unknown")
        raise RuntimeError(
            f"HuggingFace model is loading (estimated wait: {est}s). "
            "Please retry shortly."
        )

    if not response.ok:
        raise RuntimeError(
            f"HuggingFace API error {response.status_code}: "
            f"{response.text[:300]}"
        )

    try:
        results = response.json()
    except ValueError:
        raise RuntimeError(
            f"HuggingFace returned non-JSON response: {response.text[:200]}"
        )

    if not isinstance(results, list) or len(results) == 0:
        raise RuntimeError(
            f"Unexpected HuggingFace response format: {results}"
        )

    # Sort descending by confidence score
    sorted_results = sorted(results, key=lambda x: x.get("score", 0.0), reverse=True)
    top = sorted_results[0]

    return {
        "label": top.get("label", "Unknown"),
        "confidence": float(top.get("score", 0.0)),
        "all_predictions": sorted_results,
        "model_used": model_id,
    }


# ---------------------------------------------------------------------------
# Groq — structured clinical report generation (Llama 3.3 70B)
# ---------------------------------------------------------------------------

def generate_clinical_report(
    label: str,
    confidence: float,
    image_type: str,
) -> str:
    """
    Call the Groq API with a structured radiology prompt and return a
    detailed clinical report string.

    Args:
        label      : Top classification label from HuggingFace.
        confidence : Confidence score (0.0–1.0).
        image_type : 'jpg', 'jpeg', 'png', or 'dcm'.

    Returns:
        Clinical report as a plain text / markdown string.

    Raises:
        ValueError   — missing GROQ_API_KEY.
        RuntimeError — Groq API returned an error.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set. "
            "Get a free key at https://console.groq.com/keys"
        )

    model_name = os.getenv("GROQ_MODEL", _DEFAULT_GROQ_MODEL)

    prompt = f"""You are a senior clinical radiologist AI assistant operating within a certified medical decision-support system.

You have received the following automated image classification result:

  Image Format   : {image_type.upper()}
  Disease Label  : {label}
  Confidence     : {confidence * 100:.1f}%

Please generate a structured clinical radiology report with EXACTLY the following sections:

---

**1. CLINICAL INTERPRETATION**
Explain what the AI-detected label means clinically. Describe the typical radiological appearance and what it implies about the patient's condition.

**2. DIAGNOSTIC IMPRESSION**
State the most likely diagnosis based on the classification result and confidence level. Note if the confidence level affects diagnostic certainty.

**3. CLINICAL SIGNIFICANCE & URGENCY**
Classify the urgency as one of: ROUTINE | URGENT | EMERGENCY
Explain the clinical significance and potential consequences if untreated.

**4. RECOMMENDED ACTIONS**
Provide specific, actionable next steps for the treating physician (e.g., correlate with clinical symptoms, additional imaging, specialist referral, lab workup, treatment considerations).

**5. DIFFERENTIAL DIAGNOSES**
List 2–3 alternative diagnoses that should be considered or ruled out.

**6. LIMITATIONS & DISCLAIMER**
Note the key limitations of this AI-assisted analysis (e.g., lack of clinical context, image quality, model training distribution).

---

⚠️ IMPORTANT: This report is generated by an AI model to ASSIST, not replace, a licensed radiologist or clinician. All findings must be reviewed and verified by a qualified medical professional before any clinical decision is made.
"""

    try:
        client = Groq(api_key=api_key)
        chat_completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.4,
        )
    except Exception as exc:
        raise RuntimeError(f"Groq API error: {exc}") from exc

    # Extract text from the response
    if chat_completion and chat_completion.choices:
        return chat_completion.choices[0].message.content.strip()

    raise RuntimeError(f"Unexpected Groq response structure: {chat_completion}")
