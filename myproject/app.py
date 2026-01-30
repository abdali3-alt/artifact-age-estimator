import streamlit as st
import openai
import base64
import os
import json
import uuid
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

st.set_page_config(page_title="Artifact Age Estimator", page_icon="📜", layout="wide")

api_key = os.getenv("OPENAI_API_KEY")

HISTORY_FILE = "history.json"
IMAGES_DIR = "saved_images"
os.makedirs(IMAGES_DIR, exist_ok=True)


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def safe_ext(mime_type: str) -> str:
    if mime_type == "image/png":
        return "png"
    return "jpg"


def save_uploaded_image_locally(uploaded_file) -> tuple[str, str]:
    mime_type = uploaded_file.type or "image/jpeg"
    ext = safe_ext(mime_type)

    time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{time_str}_{unique_id}.{ext}"
    image_path = os.path.join(IMAGES_DIR, filename)

    with open(image_path, "wb") as out:
        out.write(uploaded_file.getvalue())

    return image_path, uploaded_file.name


def delete_image_file(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# ---------------- Session state ----------------
if "history" not in st.session_state:
    st.session_state.history = load_history()

if "selected_history_index" not in st.session_state:
    st.session_state.selected_history_index = None


st.title("⏳ Artifact Age Estimator")
st.markdown("Upload an image and get analysis + preservation guidance. History is saved locally.")

# ---------------- Sidebar: History ----------------
st.sidebar.header("🕘 History")

if st.session_state.history:
    labels = [
        f"{i+1}. {item['time']} — {item['name']}"
        for i, item in enumerate(st.session_state.history)
    ]

    # ✅ No auto-selection (so nothing appears unless user chooses)
    selected_label = st.sidebar.selectbox(
        "Saved Analyses",
        options=["— Select an item —"] + labels[::-1],  # newest first
        index=0,
        key="history_selectbox",
    )

    if selected_label == "— Select an item —":
        st.session_state.selected_history_index = None
    else:
        reversed_index = labels[::-1].index(selected_label)
        selected_index = (len(labels) - 1) - reversed_index
        st.session_state.selected_history_index = selected_index

    c1, c2 = st.sidebar.columns(2)

    with c1:
        if st.sidebar.button("🗑️ Delete", use_container_width=True):
            idx = st.session_state.selected_history_index
            if idx is not None and 0 <= idx < len(st.session_state.history):
                item = st.session_state.history[idx]
                delete_image_file(item.get("image_path", ""))
                st.session_state.history.pop(idx)
                save_history(st.session_state.history)
                st.session_state.selected_history_index = None
                st.rerun()

    with c2:
        if st.sidebar.button("🧹 Clear All", use_container_width=True):
            for item in st.session_state.history:
                delete_image_file(item.get("image_path", ""))
            st.session_state.history = []
            save_history(st.session_state.history)
            st.session_state.selected_history_index = None
            st.rerun()

    idx = st.session_state.selected_history_index
    if idx is not None and 0 <= idx < len(st.session_state.history):
        item = st.session_state.history[idx]

        st.sidebar.download_button(
            "⬇️ Download Selected Text",
            data=item["result"],
            file_name=f"artifact_analysis_{item['time'].replace(':','-')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

        with st.sidebar.expander("👁️ Preview Selected History", expanded=False):
            st.markdown(f"**Time:** {item['time']}")
            st.markdown(f"**File:** {item['name']}")

            image_path = item.get("image_path", "")
            if image_path and os.path.exists(image_path):
                st.image(image_path, caption="Saved Image", use_container_width=True)
            else:
                st.warning("Saved image file not found on disk.")

            st.markdown("---")
            st.markdown(item["result"])
else:
    st.sidebar.info("No history yet.")


# ---------------- Upload + New Analysis (Main Page) ----------------
uploaded_file = st.file_uploader("Choose an image...", type=["png", "jpg", "jpeg"])

prompt = """
You are an expert in archaeology, artifact conservation, and historical landmark analysis.

IMPORTANT FORMAT RULES:
- Use Markdown.
- Each numbered section must start on a new line.
- Under each section, use bullet points.

Analyze the attached image carefully and infer as much information as possible from visual evidence alone.

Rules:
- Use ONLY what you can see in the image.
- If uncertain, give up to 3 likely possibilities and explain why.
- Do NOT refuse to answer unless it is truly impossible.
- Always include a confidence level (High / Medium / Low).

Return your answer exactly in this structure:

1 **Artifact / Structure type:**
2 **Estimated period:**
3 **Approximate age:**
4 **Probable location / civilization:**
5 **Confidence level:**
6 **Visual reasoning:**

7 **Artifact Type Identification:**
8 **Material Analysis:**
9 **Environmental Conditions:**
10 **Handling Guidelines:**
11 **Cleaning Advice:**
12 **Long-Term Preservation Tips:**
13 **Risk Warnings:**
"""

if uploaded_file is not None:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📷 Uploaded Image")
        st.image(uploaded_file, use_container_width=True)

    with col2:
        st.subheader("🔍 New Analysis")

        if st.button("Estimate Artifact Age", type="primary", use_container_width=True):
            if not api_key:
                st.error("⚠️ Please set OPENAI_API_KEY in your .env file!")
            else:
                with st.spinner("🔄 Analyzing image..."):
                    try:
                        client = openai.OpenAI(api_key=api_key)

                        # Save image locally for history
                        saved_image_path, original_name = save_uploaded_image_locally(uploaded_file)

                        # Encode image for API
                        bytes_data = uploaded_file.getvalue()
                        base64_image = base64.b64encode(bytes_data).decode("utf-8")
                        mime_type = uploaded_file.type or "image/jpeg"

                        response = client.chat.completions.create(
                            model="gpt-4.1",
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        {
                                            "type": "image_url",
                                            "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                                        },
                                    ],
                                }
                            ],
                            max_tokens=1600,
                            temperature=0.3,
                        )

                        result = response.choices[0].message.content or ""

                        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        st.session_state.history.append(
                            {
                                "time": time_str,
                                "name": original_name,
                                "image_path": saved_image_path,
                                "result": result,
                            }
                        )
                        save_history(st.session_state.history)

                        st.success("✅ Analysis Complete! Saved to History.")
                        st.markdown("---")
                        st.markdown(result)

                    except openai.AuthenticationError:
                        st.error("❌ Invalid API key.")
                    except openai.RateLimitError:
                        st.error("❌ Rate limit exceeded.")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
else:
    st.info("👆 Upload a new image to create a new analysis. History previews are in the sidebar.")



st.markdown("@Made by Alsharif Abdulrahman Alabdali")