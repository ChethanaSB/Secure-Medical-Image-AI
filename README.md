# MedScan AI: Secure Medical Imaging & Diagnostic Pipeline

![MedScan AI Banner](https://img.shields.io/badge/Status-Active-success) ![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Flask](https://img.shields.io/badge/Flask-Backend-black) ![Supabase](https://img.shields.io/badge/Supabase-Auth-green) ![Groq](https://img.shields.io/badge/Groq-Llama%203.3-orange)

MedScan AI is a full-stack, highly secure medical image analysis platform. It provides healthcare professionals with a safe environment to upload, encrypt, and analyze patient medical images (like Chest X-Rays and MRIs). The system leverages cutting-edge visual AI for disease detection and Large Language Models (LLMs) to automatically generate structured clinical reports.

---

## ✨ Key Features

*   **Bank-Grade Image Encryption:** Medical images are encrypted using AES-256-CBC before they ever touch the hard drive.
*   **Cryptographic Data Integrity:** Every image generates a SHA-256 checksum to guarantee it has not been tampered with or corrupted over time.
*   **Hybrid Authentication:** Powered by Supabase for enterprise-grade secure registration, login, and JWT validation, synchronized with a local SQLite database for role-based access control (RBAC).
*   **Automated AI Diagnostics:** Integrates with Hugging Face Vision models to instantly classify X-Rays and scans (e.g., detecting Pneumonia).
*   **Generative AI Clinical Reports:** Feeds the visual classification data into Groq's blazing-fast Llama 3.3 70B model to generate detailed, structured, and actionable medical reports.
*   **Admin Dashboard & Audit Logs:** A comprehensive dashboard for administrators to monitor network traffic, view registered users, and track every single action taken on the platform via secure audit trails.

---

## 🛠️ Technology Stack

| Component | Technology Used | Purpose |
| :--- | :--- | :--- |
| **Backend** | Python, Flask, Werkzeug | REST API, core application logic, encryption algorithms. |
| **Frontend** | Vanilla HTML, CSS, JS | Lightweight, lightning-fast UI with modern glassmorphism design. |
| **Authentication** | Supabase (GoTrue API) | Secure user registration, password management, and JWT token issuing. |
| **Database** | SQLite, SQLAlchemy | Storing patient metadata, image hashes, AI predictions, and audit logs. |
| **Visual AI** | Hugging Face Inference API | Running state-of-the-art Vision Transformers (ViT) for image classification. |
| **Language AI**| Groq API (Llama 3.3 70B)| Generating human-readable, structured clinical reports. |
| **Security** | PyCryptodome (AES/SHA) | Military-grade encryption and cryptographic hashing. |

---

## 🔒 How It Works: The Image Pipeline

This project was built with patient privacy and HIPAA compliance concepts in mind. Here is exactly what happens to a medical image from the moment it is uploaded:

### Phase 1: Upload & Encryption
1. **The Upload:** A doctor selects a patient and drops an image file (JPG, PNG, or DICOM) into the web interface.
2. **In-Memory Buffer:** The Flask backend receives the raw image bytes into memory.
3. **AES-256 Encryption:** Before saving, the backend uses a secure `AES_KEY` to completely scramble the image bytes using Cipher Block Chaining (CBC). 
4. **Data Integrity Hashing:** The system calculates a unique SHA-256 hash of the *encrypted* file.
5. **Storage:** The scrambled, unreadable bytes are saved to the `uploads/` folder. The SHA-256 hash and metadata are saved to the SQLite database. *If a hacker steals the `uploads/` folder, they will only see random noise.*

### Phase 2: Decryption & Viewing
1. **The Request:** The doctor navigates to the Viewer page for that image.
2. **Integrity Check:** The backend reads the encrypted file from disk, recalculates its SHA-256 hash, and compares it to the database. If they match, the file is verified as untampered.
3. **In-Memory Decryption:** The backend decrypts the file back into a visible image entirely in RAM. *The decrypted image is never saved to the hard drive.*
4. **Secure Delivery:** The image is sent to the frontend as a Base64 string encoded within the protected API response.

### Phase 3: AI Analysis
1. **Visual Classification:** The decrypted image bytes are sent securely to the **Hugging Face API**. The Vision model analyzes the pixels and returns a label (e.g., "Pneumonia") and a confidence score (e.g., "94.5%").
2. **Report Generation:** The label and score are sent to the **Groq API (Llama 3.3)**. The LLM acts as a senior radiologist, taking the classification and generating a structured report featuring Clinical Interpretations, Urgency Levels, and Recommended Actions.
3. **Persistence:** The final report is saved to the local database so it doesn't need to be regenerated every time the doctor views the image.

---

## 🌟 How This Project Stands Out

1. **Security-First Architecture:** Unlike many medical AI wrappers that just send raw data to an API, this system treats local storage as hostile. By enforcing AES-256 encryption at rest, it demonstrates a deep understanding of medical data compliance.
2. **Agentic AI Handoff:** It doesn't just use one AI. It uses a specialized *Visual Model* to "see" the image, and then hands those findings off to an *LLM (Language Model)* to "think" and write the report, mimicking a real hospital workflow.
3. **Hybrid Auth Design:** It expertly bridges the gap between modern cloud services (Supabase) and local data integrity (SQLite foreign keys), showing advanced system integration skills.

---

## 🚀 Future Scope

*   **Native DICOM Rendering:** Implement a library like Cornerstone.js on the frontend to allow doctors to manipulate window/level, zoom, and pan on native `.dcm` files directly in the browser.
*   **Federated Learning:** Allow the local system to train on the encrypted images without ever exposing the raw data to the central cloud.
*   **Multi-Modal AI:** Upgrade the Groq prompt to take in both the image classification *and* the patient's textual medical history for highly personalized diagnostic reports.
*   **Cloud Object Storage:** Migrate the encrypted `uploads/` folder to AWS S3 or Supabase Storage for infinite scalability.
