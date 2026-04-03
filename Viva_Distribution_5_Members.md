# Lumen Vault Viva Distribution For 5 Members

This file explains the complete Lumen Vault project in a way that 5 team members can present it during viva. Each member gets one clear section. The sections marked as `Very Important` should be explained with extra confidence because they represent the core working of the project.

---

## Member 1: Project Introduction, Problem Statement, and Overall Flow
**Importance:** `Very Important`

### What to explain
- Lumen Vault is a study assistant workspace for diploma/polytechnic students.
- It combines syllabus, previous year question papers, uploaded study materials, AI help, and MCQ generation in one system.
- The project is built mainly with:
  - Python Flask for backend
  - HTML, CSS, and JavaScript for frontend
  - PDF parsing and OCR for reading documents
  - AI integration for answers and quiz generation

### Problem solved by the project
- Students usually search syllabus, study notes, question papers, and explanations in different places.
- This project brings all of them into one platform.
- It helps in exam preparation, quick revision, theory answer writing, and practice through MCQs.

### Complete workflow of the system
1. Subject data is loaded from the library index.
2. Students filter and choose a subject.
3. They can open syllabus, previous papers, or uploaded materials.
4. AI Studio gives subject-focused help.
5. MCQs are generated from question papers or uploaded PDFs.
6. Progress, chats, notes, and quiz history are stored for each student.

### Key points to say in viva
- This is not just a file viewer, it is an integrated study platform.
- The main strength is combining academic content with AI assistance.
- The project supports both structured academic study and interactive learning.

---

## Member 2: Backend Architecture and Data Management
**Importance:** `Very Important`

### What to explain
- The backend is written in Flask and controlled mainly by `lumen_vault.py`.
- It handles:
  - subject library loading
  - question paper mapping
  - uploaded material storage
  - AI API routes
  - MCQ generation routes
  - health and diagnostics routes

### Core backend responsibilities
- Reads `library_index.json`
- Creates unique subject keys
- Maps subjects, papers, and materials for fast lookup
- Stores uploaded PDFs in subject-wise folders
- Saves uploaded material metadata in `materials_index.json`

### Important backend logic
- `subject_key(...)` creates a unique key using program code, paper code, and subject name.
- material index functions load and save JSON records.
- Flask routes connect frontend requests with the backend logic.

### Important routes to mention
- `/lumen_vault/api/health`
- `/lumen_vault/api/chat`
- `/lumen_vault/api/materials/upload`
- `/lumen_vault/api/materials`
- `/lumen_vault/api/mcq`
- `/lumen_vault/api/diagnostics`

### Key viva points
- Backend is the brain of the system.
- It connects static academic data, uploaded PDFs, and AI responses.
- JSON indexing is used for lightweight and fast data handling.

---

## Member 3: PDF Handling, OCR, and Material Upload System
**Importance:** `Very Important`

### What to explain
- Students can upload subject-wise PDFs such as:
  - question files
  - subject tests
  - book or study material
- The backend checks whether the file is a valid PDF and stores it safely.

### PDF processing logic
- Native PDF text extraction is tried first.
- If the PDF is scanned or weak in text quality, OCR is used.
- The backend compares native text and OCR text, then keeps the better result.

### Why this part is important
- Many academic PDFs are scanned images, not typed text.
- Without OCR, AI and MCQ generation would fail for many uploaded materials.
- This makes the system practical for real student documents.

### Upload workflow
1. Student selects subject and material type.
2. Frontend sends the PDF using `FormData`.
3. Backend stores the PDF in a subject folder.
4. Text is extracted and validated.
5. If readable, metadata is saved in the material index.
6. The uploaded PDF becomes available for study support and MCQ generation.

### Key viva points
- OCR support is one of the strongest technical parts of the project.
- The system rejects unreadable PDFs to maintain quality.
- Uploaded material is organized subject-wise for efficient retrieval.

---

## Member 4: AI Integration and Answer Generation
**Importance:** `Very Important`

### What to explain
- AI Studio gives answers based on the selected subject.
- The project supports multiple AI backends with fallback logic.
- The backend order can include:
  - Ollama
  - OpenAI
  - llama.cpp

### How AI works in this project
- User asks a question from the frontend.
- Backend finds the related subject.
- Relevant syllabus or material snippets are collected.
- A system prompt is built according to the selected mode:
  - study help
  - theory answer
  - step wise
  - answer paper
- The AI backend generates the reply.

### Why this is important
- AI is not answering blindly.
- It is grounded using subject-specific information when available.
- This makes the answers more useful for exam preparation.

### Diagnostics and health
- The project includes health check and AI diagnostics.
- These help test whether API keys, token responses, and backend providers are working.

### Key viva points
- AI is controlled through fallback logic, not a single backend.
- The system can support cloud AI and local/offline AI.
- Diagnostics make the system easier to troubleshoot during deployment.

---

## Member 5: Frontend, User Experience, Login, and MCQ Module
**Importance:** `Important`

### What to explain
- The frontend is built with HTML, CSS, and JavaScript.
- It includes sections such as:
  - dashboard
  - library
  - papers
  - syllabus
  - materials
  - MCQ
  - history
  - saved
  - AI Studio
  - AI diagnostics

### Student login and personal data
- A login page is provided for each student.
- Students enter name and student ID.
- Their local data is stored separately in the browser, including:
  - chats
  - bookmarks
  - notes
  - solved status
  - quiz history

### MCQ system
- MCQs can be generated from:
  - question papers
  - uploaded materials
- The system tracks:
  - score
  - percentage
  - subject
  - quiz history
- Wrong behavior such as always putting the first option as correct was fixed by randomizing answer positions.
- Noisy paper instructions are filtered to avoid nonsense MCQs.

### Key viva points
- Frontend is designed as a complete student workspace.
- Personal data separation improves usability for multiple students.
- MCQ practice adds interactive learning, not just passive reading.

---

## Final Viva Conclusion
If the examiner asks for the most important parts, the team should give extra attention to:

1. `Member 1` for project overview and complete workflow
2. `Member 2` for backend architecture and API routes
3. `Member 3` for PDF extraction and OCR
4. `Member 4` for AI integration and backend fallback

`Member 5` is also important because it explains how students actually use the system, especially login and MCQ features.

---

## Suggested Order For Presentation
1. Member 1 starts with project overview and objectives.
2. Member 2 explains backend and data flow.
3. Member 3 explains PDF upload and OCR.
4. Member 4 explains AI working and diagnostics.
5. Member 5 ends with frontend, login, MCQ module, and final user benefits.

This order gives a smooth flow from introduction to technical implementation to user experience.
