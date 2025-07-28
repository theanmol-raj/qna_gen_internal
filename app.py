import streamlit as st
import pandas as pd
import openai
import os
import io
import time
import anthropic
import boto3
import json


st.set_page_config(page_title="Custom Prompt Q&A Generator", layout="wide")

# ─── SIDEBAR ───────────────────────────────────────────────────────────────

AWS_ACCESS_KEY_ID = st.secrets["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
AWS_REGION = st.secrets["AWS_REGION"]

st.sidebar.header("🤖 Model & API Configuration")

# Define model options with provider info
model_options = {
    "GPT-4o (OpenAI)": {"provider": "openai", "model": "gpt-4o"},
    "GPT-3.5 Turbo (OpenAI)": {"provider": "openai", "model": "gpt-3.5-turbo"},
    "Claude Sonnet 3.7" : {"provider" : "anthropic" , "model": "anthropic.claude-3-7-sonnet-20250219-v1:0"},
}
bedrock = boto3.client("bedrock-runtime", region_name=st.secrets["AWS_REGION"],
    aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"])

model_label = st.sidebar.selectbox("Choose a model", list(model_options.keys()))
selected_model_info = model_options[model_label]
provider = selected_model_info["provider"]
selected_model = selected_model_info["model"]

# Dynamic API Key input based on provider
api_key = st.sidebar.text_input(
    f"{provider.capitalize()} API Key",
    type="password",
    help=f"Enter your API key for {provider.capitalize()}",
)


st.sidebar.header("✍️ Prompt Template")
default_template = """
From the provided text "Question : {question} Answer:{answer}" generate a question and answer to that question

<rules>
- Strictly ensure that 100% of the text "question" "answer" given is utilised in formation of response
- While ensuring flow use a language that is understandable and comprehendible to even a 5 year old
- In the Answer, ensure that it's written in a flow using second person pronouns e.g. "you" wherever relevant
- Frame the question as a person sharing/asking/enquiring/venting out their situation in 15–30 words
- The Answer should follow a Reddit-style sentence structuring
- Ensure that the answer have context for all the things mentioned such as stories or references
- Formulate response keeping in mind that you are a mental health chatbot Healo answering user queries (generated question) but dont explicitly mention that in the response
- Keep the Answer within 150-200 words while capturing all the content given in the text "question" "answer"
- Strictly give the Answer in a paragraph format only ensuring flow and connectivity in the content
- Frequently use "....", "-", ":" and other such grammatical components to make the structure of the answer
</rules>

Output Format:
Question:
Answer:
"""
prompt_template = st.sidebar.text_area(
    "Edit your prompt below (use Question placeholder :{question}): Answer placeholder :{answer} ",
    value=default_template,
    height=300
)

st.sidebar.header("📁 Upload")
uploaded_file = st.sidebar.file_uploader(
    "Upload an Excel file (.xlsx)",
    type=["xlsx"]
)

# ─── FUNCTION ─────────────────────────────────────────────────────────────


def reddit_response(ques: str, ans: str, template: str, provider: str, model: str, api_key: str) -> str:
    prompt = template.replace("{question}", ques).replace("{answer}", ans)

    try:
        if provider == "openai":

            openai.api_key = api_key
            resp = openai.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            return resp.choices[0].message.content

        elif provider == "anthropic":
            model_id = model
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1024,
                
            }
            response = bedrock.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
                
          
            )
            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']

        else:
            return "Unsupported provider."

    except Exception as e:
        st.error(f"Generation error: {e}")
        return "Question: \nAnswer:"


# ─── MAIN ─────────────────────────────────────────────────────────────────
if uploaded_file and api_key:
    st.header("🚀 Ready to Generate")
    xlsx = pd.ExcelFile(uploaded_file)
    sheet_names = xlsx.sheet_names
    selected_sheet = st.selectbox("Select a sheet to process", sheet_names)

    df = pd.read_excel(xlsx, sheet_name=selected_sheet)
    st.write(f"### Preview of your data from `{selected_sheet}`", df.head())

    if st.button("▶️ Generate Q&A for each row"):
        start_time = time.time()
        questions, answers = [], []
        progress = st.progress(0)
        status_text = st.empty()  # Placeholder to show current row progress
        total = len(df)

        for i, row in df.iterrows():
            status_text.markdown(f"**Processing row {i + 1} of {total}...**")

            try:
                ques = str(row.get("Questions", ""))
                ans = str(row.get("Answers", ""))
                resp = reddit_response(ques, ans, prompt_template, provider, selected_model, api_key)

                parts = resp.split("Answer:")
                q = parts[0].replace("Question:", "").strip()
                a = parts[1].strip() if len(parts) > 1 else ""
                questions.append(q)
                answers.append(a)

            except Exception as e:
                st.error(f"Error at row {i + 1}: {e}")
                questions.append("")
                answers.append("")

            progress.progress((i + 1) / total)

        df["Generated questions"] = questions
        df["Generated answers"] = answers

        st.success(f"Done in {time.time() - start_time:.2f}s")
        status_text.markdown("**✅ All rows processed**")
        st.write("### Results", df)

        towrite = io.BytesIO()
        df.to_excel(towrite, index=False, engine="openpyxl")
        towrite.seek(0)
        st.download_button(
            label="📥 Download as Excel",
            data=towrite,
            file_name="generated_qa_output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

elif not api_key:
    st.warning(f"Please enter your {provider} API key in the sidebar.")
else:
    st.info("Upload an Excel file to get started.")
