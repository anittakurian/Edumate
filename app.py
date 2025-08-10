import streamlit as st
import google.generativeai as genai
import PyPDF2
from gtts import gTTS
import os
import re
from dotenv import load_dotenv

# Load API Key 
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("API key not found. Please set GEMINI_API_KEY in your .env file.")
else:
    genai.configure(api_key=api_key)

# Initialize Gemini models
summary_model = genai.GenerativeModel('models/gemini-1.5-flash')
flashcard_model = genai.GenerativeModel('models/gemini-1.5-flash')

# Utility Functions 
def extract_text_from_pdf(uploaded_file):
    reader = PyPDF2.PdfReader(uploaded_file)
    return "\n".join([page.extract_text() or "" for page in reader.pages])

def chunk_text(text, max_chars=3000):
    words = text.split()
    chunks, current_chunk, current_len = [], [], 0
    for word in words:
        if current_len + len(word) + 1 > max_chars:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_len = len(word) + 1
        else:
            current_chunk.append(word)
            current_len += len(word) + 1
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def get_summary(text):
    chunks = chunk_text(text, max_chars=3000)
    summaries = []
    for i, chunk in enumerate(chunks):
        try:
            response = summary_model.generate_content(f"Please provide a concise summary:\n\n{chunk}")
            summaries.append(response.text.strip())
        except Exception as e:
            st.error(f"Error generating summary for chunk {i+1}: {e}")
    if len(summaries) > 1:
        try:
            combined_summary = " ".join(summaries)
            response = summary_model.generate_content(f"Combine into one cohesive summary:\n\n{combined_summary}")
            return response.text.strip()
        except:
            return combined_summary
    return summaries[0] if summaries else "Could not generate summary."

def generate_flashcards(text):
    if len(text) > 4000:
        text = text[:4000]
    prompt = f"""
    Create 15 flashcards in Q: / A: format from the following text:
    {text}
    """
    try:
        response = flashcard_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        st.error(f"Error generating flashcards: {e}")
        return ""

def parse_flashcards(flashcards_text):
    pattern = r"Q:\s*(.*?)\s*A:\s*(.*?)(?=\nQ:|\Z)"
    matches = re.findall(pattern, flashcards_text, re.DOTALL)
    return [{"question": q.strip(), "answer": a.strip()} for q, a in matches]

def tts_google(text):
    try:
        tts = gTTS(text=text, lang='en')
        filename = "output.mp3"
        tts.save(filename)
        return filename
    except Exception as e:
        st.error(f"TTS failed: {e}")
        return None

def _generate_flashcards_and_reset_quiz(extracted_text):
    if extracted_text:
        with st.spinner("Creating flashcards..."):
            st.session_state.flashcards_text = generate_flashcards(extracted_text)
            st.session_state.flashcards = parse_flashcards(st.session_state.flashcards_text)
            st.session_state.quiz_index = 0
            st.session_state.score = 0
            st.session_state.quiz_done = False
            st.session_state.feedback_message = ""
            st.session_state.display_correct_answer = ""
            st.session_state.quiz_active = False
    else:
        st.warning("No text extracted from PDF.")

#  Streamlit UI 
st.set_page_config(page_title="EduMate - AI Summarizer & Quiz", layout="centered")
st.title("EduMate - AI Summarization Assistant & Quiz")
st.markdown("Powered by Google Gemini (Free Tier)")

# Init states
for key in ["quiz_index", "score", "quiz_done", "show_answer", "flashcards", 
            "summary", "flashcards_text", "extracted_text", "quiz_active", 
            "last_uploaded_file", "feedback_message", "display_correct_answer"]:
    if key not in st.session_state:
        st.session_state[key] = 0 if "score" in key or "index" in key else False if "active" in key else ""

option = st.radio("Choose Input Type", ["Upload PDF", "Upload Audio (coming soon)"])

if option == "Upload PDF":
    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
    if uploaded_file:
        if uploaded_file != st.session_state.last_uploaded_file:
            with st.spinner("Extracting text..."):
                st.session_state.extracted_text = extract_text_from_pdf(uploaded_file)
                st.session_state.last_uploaded_file = uploaded_file
                st.session_state.summary = ""
                st.session_state.flashcards = []
                st.session_state.flashcards_text = ""
        st.subheader("Extracted Text (first 1000 chars)")
        st.text_area("", st.session_state.extracted_text[:1000], height=200, disabled=True)

        if st.button("Summarize Text"):
            if st.session_state.extracted_text:
                with st.spinner("Summarizing..."):
                    st.session_state.summary = get_summary(st.session_state.extracted_text)
            else:
                st.warning("No text extracted.")

        if st.session_state.summary:
            st.subheader("Summary")
            st.write(st.session_state.summary)
            st.button("Generate Flashcards", on_click=lambda: _generate_flashcards_and_reset_quiz(st.session_state.extracted_text))
            if st.button("Listen to Summary"):
                audio_path = tts_google(st.session_state.summary)
                if audio_path:
                    st.audio(audio_path, format="audio/mp3")

        if st.session_state.flashcards_text and not st.session_state.quiz_active:
            st.subheader("Flashcards Review")
            st.text_area("Review", st.session_state.flashcards_text, height=300, disabled=True)
            if st.session_state.flashcards:
                if st.button("Start Quiz"):
                    st.session_state.quiz_active = True
                    st.session_state.quiz_index = 0
                    st.session_state.score = 0
                    st.session_state.quiz_done = False
                    st.rerun()

        if st.session_state.flashcards:
            st.subheader("Quiz Time!")
            if st.session_state.quiz_active and not st.session_state.quiz_done:
                card = st.session_state.flashcards[st.session_state.quiz_index]
                st.markdown(f"#### Question {st.session_state.quiz_index + 1} of {len(st.session_state.flashcards)}:")
                st.write(f"**{card['question']}**")
                user_answer = st.text_input("Your Answer:", key=f"answer_{st.session_state.quiz_index}")
                if st.button("Submit Answer"):
                    correct = card["answer"].lower().strip()
                    if user_answer.lower().strip() == correct:
                        st.session_state.feedback_message = "Correct!"
                        st.session_state.score += 1
                        st.session_state.display_correct_answer = ""
                    else:
                        st.session_state.feedback_message = "Incorrect!"
                        st.session_state.display_correct_answer = card["answer"]
                    st.rerun()
                if st.session_state.feedback_message:
                    if "Correct" in st.session_state.feedback_message:
                        st.success(st.session_state.feedback_message)
                    else:
                        st.error(st.session_state.feedback_message)
                if st.session_state.display_correct_answer:
                    st.info(f"Correct Answer: {st.session_state.display_correct_answer}")
                if st.button("Next Question"):
                    st.session_state.quiz_index += 1
                    if st.session_state.quiz_index >= len(st.session_state.flashcards):
                        st.session_state.quiz_done = True
                        st.session_state.quiz_active = False
                    st.session_state.feedback_message = ""
                    st.session_state.display_correct_answer = ""
                    st.rerun()

            elif st.session_state.quiz_done:
                st.success(f"Quiz completed! 🎉 Your score: {st.session_state.score}/{len(st.session_state.flashcards)}")
                if st.button("Restart Quiz"):
                    st.session_state.quiz_index = 0
                    st.session_state.score = 0
                    st.session_state.quiz_done = False
                    st.session_state.quiz_active = True
                    st.rerun()

elif option == "Upload Audio (coming soon)":
    st.info("Speech-to-summary support will be added soon.")
