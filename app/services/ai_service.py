from __future__ import annotations

import json
import time

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from app.core.config import settings
from app.utils.helpers import split_text

# Maximum retries for rate-limited requests
MAX_RETRIES = 3
RETRY_BASE_DELAY = 8  # seconds


# ═══════════════════════════════════════════════════════════════
#  PROMPT TEMPLATES — Original artifact prompts (kept for compat)
# ═══════════════════════════════════════════════════════════════

ARTIFACT_PROMPTS = {
    "study_guide": (
        "Create a comprehensive Study Guide based on the provided sources. "
        "Include key concepts, definitions, important terms, and review questions. "
        "Organize by topic. Use clear headings and bullet points."
    ),
    "faq": (
        "Generate a detailed FAQ document from the provided sources. "
        "Create 10-15 questions and answers that cover the most important topics. "
        "Make answers thorough but concise."
    ),
    "timeline": (
        "Create a chronological Timeline of key events, milestones, or developments "
        "mentioned in the provided sources. Format as a clear ordered list with dates/periods."
    ),
    "briefing_doc": (
        "Write a professional Briefing Document summarizing the key information from "
        "the provided sources. Include an executive summary, key findings, and conclusions. "
        "Keep it structured and formal."
    ),
    "table_of_contents": (
        "Create a structured Table of Contents / outline organizing all the major topics "
        "and subtopics found in the provided sources. Use clear hierarchy."
    ),
    "audio_overview": (
        "Write a conversational podcast-style script between two hosts discussing the "
        "key concepts from the provided sources. Make it engaging, educational, and natural. "
        "Use a back-and-forth dialogue format. Start with an introduction and end with "
        "a summary of key takeaways. Label speakers as 'Host A' and 'Host B'."
    ),
}


# ═══════════════════════════════════════════════════════════════
#  MODE-AWARE SYSTEM INSTRUCTIONS
# ═══════════════════════════════════════════════════════════════

MODE_INSTRUCTIONS = {
    "Student Mode": (
        "You are in STUDENT MODE. Keep your answers simple, clear, and easy to understand. "
        "Use analogies, examples, and step-by-step explanations. Avoid jargon. "
        "Focus on helping a beginner learn the material effectively."
    ),
    "Developer Mode": (
        "You are in DEVELOPER MODE. Provide detailed, technical explanations. "
        "Include implementation details, code snippets where relevant, data structures, "
        "API insights, and advanced analysis. Be thorough and precise."
    ),
}

CRITICAL_THINKING_INSTRUCTION = (
    "CRITICAL THINKING: Do not merely summarize. Analyze, compare, question, and explain deeply. "
    "Identify assumptions, evaluate evidence, explore alternative perspectives, "
    "and provide well-reasoned conclusions. Challenge surface-level understanding."
)


class AIService:
    """Centralized AI service using OpenRouter for all content generation."""

    def __init__(self):
        self.enabled = bool(settings.openrouter_api_key) and OpenAI is not None
        self.import_error = None if OpenAI is not None else "openai package is not installed."
        if self.enabled:
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.openrouter_api_key,
            )
            self.model_name = settings.openrouter_model
        else:
            self.client = None
            self.model_name = None

    @staticmethod
    def _classify_generation_error(exc: Exception) -> tuple[str, bool]:
        """Return a user-facing message and whether the error is retryable."""
        error_text = str(exc)
        lowered = error_text.lower()

        if "quota exceeded" in lowered or "insufficient credits" in lowered:
            return (
                "OpenRouter API credits are exhausted. "
                "Add credits at https://openrouter.ai or use a different API key, "
                "then update OPENROUTER_API_KEY in your .env and restart the app.",
                False,
            )

        if "api key" in lowered and ("invalid" in lowered or "not valid" in lowered or "unauthorized" in lowered):
            return (
                "The configured OpenRouter API key is invalid. Replace OPENROUTER_API_KEY in your .env "
                "with a valid key and restart the app.",
                False,
            )

        if "429" in lowered or "rate limit" in lowered or "rate_limit" in lowered:
            return ("OpenRouter API rate limit exceeded. Waiting briefly before retrying.", True)

        if "502" in lowered or "503" in lowered or "timeout" in lowered:
            return ("OpenRouter API is temporarily unavailable. Retrying...", True)

        return (error_text, False)

    # ── Core generation helper ────────────────────────────────

    def _generate(self, prompt: str) -> str:
        """Send a prompt to OpenRouter and return the response text.
        
        Automatically retries on rate-limit (429) errors with exponential backoff.
        """
        if not self.enabled or not self.client:
            if self.import_error:
                raise ValueError(
                    f"{self.import_error} Run 'pip install openai'."
                )
            raise ValueError("OpenRouter API key is missing. Add it to the .env file.")

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    extra_headers={
                        "HTTP-Referer": "http://localhost:8501",
                        "X-Title": "StudyBuddy AI",
                    },
                )
                return response.choices[0].message.content.strip()
            except Exception as exc:
                last_error = exc
                message, retryable = self._classify_generation_error(exc)
                if retryable:
                    wait_time = RETRY_BASE_DELAY * (2 ** attempt)  # 8s, 16s, 32s
                    time.sleep(wait_time)
                    continue
                raise ValueError(message) from exc

        raise ValueError(
            f"OpenRouter request failed after {MAX_RETRIES} retries. "
            f"{self._classify_generation_error(last_error)[0]}"
        )

    def _mode_prefix(self, mode: str = "Student Mode") -> str:
        """Return the system instruction for the given mode."""
        return MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["Student Mode"])

    # ═══════════════════════════════════════════════════════════
    #  CHAT
    # ═══════════════════════════════════════════════════════════

    def chat(
        self,
        knowledge_base: str,
        question: str,
        chat_history: list[dict] | None = None,
        mode: str = "Student Mode",
    ) -> str:
        """Answer a question grounded in the notebook sources."""
        history_text = ""
        if chat_history:
            recent = chat_history[-10:]
            lines = []
            for msg in recent:
                role = "User" if msg["role"] == "user" else "Assistant"
                lines.append(f"{role}: {msg['content']}")
            history_text = "\n".join(lines)

        prompt = f"""{self._mode_prefix(mode)}
{CRITICAL_THINKING_INSTRUCTION}

You are StudyBuddy AI, a smart learning assistant. You help users understand their uploaded sources.

RULES:
1. ONLY answer based on the provided sources below. Never invent information.
2. When you reference information, mention which source it came from using [Source: name] notation.
3. If the sources don't contain enough information to answer, say so clearly.
4. Be thorough, accurate, and well-structured in your responses.
5. Use markdown formatting for better readability.
6. Apply critical thinking — analyze, compare, and explain deeply.

CONVERSATION HISTORY:
{history_text or "No previous messages."}

SOURCES:
{knowledge_base[:50000]}

USER QUESTION:
{question}

Respond helpfully and cite your sources."""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  SUGGESTED QUESTIONS
    # ═══════════════════════════════════════════════════════════

    def suggest_questions(self, knowledge_base: str) -> list[str]:
        """Generate suggested follow-up questions from the sources."""
        prompt = f"""Based on these sources, suggest exactly 3 interesting questions a student might ask.
Return ONLY a JSON array of 3 strings, no other text.

Sources:
{knowledge_base[:20000]}"""

        raw = self._generate(prompt)
        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)[:3]
        except (json.JSONDecodeError, IndexError):
            return [
                "What are the main concepts discussed in these sources?",
                "Can you summarize the key findings?",
                "What are the most important takeaways?",
            ]

    # ═══════════════════════════════════════════════════════════
    #  ORIGINAL ARTIFACTS (study guide, FAQ, timeline, etc.)
    # ═══════════════════════════════════════════════════════════

    def generate_artifact(self, knowledge_base: str, artifact_type: str, mode: str = "Student Mode") -> str:
        """Generate a structured artifact (study guide, FAQ, timeline, etc.)."""
        if artifact_type not in ARTIFACT_PROMPTS:
            raise ValueError(f"Unknown artifact type: {artifact_type}")

        prompt = f"""{self._mode_prefix(mode)}
{CRITICAL_THINKING_INSTRUCTION}

TASK: {ARTIFACT_PROMPTS[artifact_type]}

RULES:
1. Base everything ONLY on the provided sources.
2. Cite sources using [Source: name] when referencing specific information.
3. Use markdown formatting with proper headings, lists, and emphasis.
4. Be comprehensive and thorough.

SOURCES:
{knowledge_base[:50000]}"""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  PPT GENERATOR
    # ═══════════════════════════════════════════════════════════

    def generate_ppt_content(self, knowledge_base: str, mode: str = "Student Mode") -> str:
        """Generate slide content for a PowerPoint presentation.

        Returns structured text where each slide is separated by ---SLIDE---.
        First line of each block is the slide title.
        """
        prompt = f"""{self._mode_prefix(mode)}

Create a professional PowerPoint presentation based on the provided sources.

CRITICAL FORMAT RULES — follow these EXACTLY:
- Separate each slide with a line containing ONLY: ---SLIDE---
- First line after ---SLIDE--- is the slide TITLE (plain text, no markdown, no special characters).
- After the title, write 3-6 DETAILED bullet points for that slide.
- Each bullet point must be on its own line, starting with "- ".
- Each bullet point must be a COMPLETE SENTENCE that explains a concept clearly (15-30 words).
- Do NOT leave any slide with only a title and no bullet points.
- Do NOT use markdown formatting like ** or # in the output.
- Create exactly 10 slides.

SLIDE STRUCTURE:
---SLIDE---
Title Slide - [Main Topic Name]
- Subtitle or key tagline for the presentation
- Prepared using AI-powered analysis of uploaded sources
- Covers all major concepts comprehensively
---SLIDE---
Introduction
- Provide background context about the subject matter
- Explain why this topic is important and relevant
- Outline what will be covered in this presentation
- Set expectations for the audience
---SLIDE---
[Main Topic 1]
- Detailed explanation of the first key concept
- Supporting evidence or examples from the sources
- How this concept relates to the broader topic
- Practical applications or implications
---SLIDE---
[Main Topic 2]
- ... continue with more detailed points ...
---SLIDE---
[Continue with more content slides...]
---SLIDE---
Key Takeaways
- Summarize the most important points from the presentation
- Highlight critical insights the audience should remember
- Suggest next steps for further learning
---SLIDE---
Conclusion
- Final summary of all concepts covered
- Call to action or recommendations based on the analysis
- Resources for further reading or study

IMPORTANT: Every single slide MUST have at least 3 detailed bullet points with full sentences. Never leave a slide blank or with only a heading.

SOURCES:
{knowledge_base[:40000]}

Generate the slide content now:"""

        return self._generate(prompt)


    # ═══════════════════════════════════════════════════════════
    #  FLASHCARDS
    # ═══════════════════════════════════════════════════════════

    def generate_flashcards(self, knowledge_base: str, mode: str = "Student Mode") -> list[dict]:
        """Generate flashcard Q&A pairs. Returns list of {question, answer} dicts."""
        prompt = f"""{self._mode_prefix(mode)}

Create 10-15 flashcards based on the provided sources.
Each flashcard should have a question on one side and the answer on the other.

Return ONLY a JSON array where each item has "question" and "answer" keys.
Example: [{{"question": "What is X?", "answer": "X is..."}}]

SOURCES:
{knowledge_base[:30000]}"""

        raw = self._generate(prompt)
        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return [
                {"question": "What are the main topics covered?", "answer": "Review the source material for details."},
                {"question": "What is the key takeaway?", "answer": "The sources cover important concepts — review them carefully."},
            ]

    # ═══════════════════════════════════════════════════════════
    #  POSTER GENERATOR
    # ═══════════════════════════════════════════════════════════

    def generate_poster_content(self, knowledge_base: str, mode: str = "Student Mode") -> str:
        """Generate structured JSON content for a visual poster."""
        prompt = f"""{self._mode_prefix(mode)}

Create content for a visually appealing educational poster based on the provided sources.

Return ONLY a valid JSON object with this exact structure:
{{
  "title": "A short catchy title (max 8 words)",
  "tagline": "An engaging one-line tagline or subtitle",
  "sections": [
    {{
      "heading": "Section Heading",
      "points": ["Key point 1", "Key point 2", "Key point 3"]
    }}
  ],
  "conclusion": "A one-line key takeaway or call to action"
}}

RULES:
- Create 4-6 sections
- Each section should have 3-5 concise bullet points
- Keep all text SHORT and impactful - this is a poster, not an essay
- Use catchy, memorable phrasing
- Make the title attention-grabbing
- The tagline should spark curiosity
- Points should be easy to scan quickly
- Return ONLY the JSON, no other text

SOURCES:
{knowledge_base[:35000]}"""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  REPORT GENERATOR
    # ═══════════════════════════════════════════════════════════

    def generate_report(self, knowledge_base: str, mode: str = "Student Mode") -> str:
        """Generate a formal academic/analytical report."""
        prompt = f"""{self._mode_prefix(mode)}
{CRITICAL_THINKING_INSTRUCTION}

Write a comprehensive academic report based on the provided sources.

Include:
## Executive Summary
## 1. Introduction
## 2. Literature Review / Background
## 3. Key Findings
## 4. Analysis & Discussion
## 5. Critical Evaluation
## 6. Conclusion & Recommendations
## References

Use formal academic tone. Cite sources using [Source: name].
Be thorough — aim for 800-1200 words.

SOURCES:
{knowledge_base[:45000]}"""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  MIND MAP
    # ═══════════════════════════════════════════════════════════

    def generate_mindmap(self, knowledge_base: str, mode: str = "Student Mode") -> str:
        """Generate a Mermaid mindmap diagram from the sources."""
        prompt = f"""{self._mode_prefix(mode)}

Create a mind map based on the provided sources using Mermaid mindmap syntax.

IMPORTANT FORMAT RULES:
- Return ONLY valid Mermaid mindmap code, nothing else.
- Start with exactly: mindmap
- Then the root node on the next line with 2 spaces indentation
- Use indentation (2 spaces per level) to show hierarchy
- Do NOT use any special characters in node labels like parentheses, brackets, quotes, colons, or backticks
- Keep node labels short - max 5 words per node
- Create 4-6 main branches from the root
- Each main branch should have 2-4 sub-branches
- Each sub-branch can have 1-3 leaf nodes
- Do NOT wrap the output in code fences or backticks

EXACT FORMAT EXAMPLE:
mindmap
  root((Central Topic))
    Branch One
      Detail A
      Detail B
    Branch Two
      Detail C
      Detail D
        Sub Detail
    Branch Three
      Detail E

SOURCES:
{knowledge_base[:30000]}

Return ONLY the mermaid mindmap code, no explanation:"""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  VIDEO OVERVIEW
    # ═══════════════════════════════════════════════════════════

    def generate_video_overview(self, knowledge_base: str, mode: str = "Student Mode") -> str:
        """Generate a video-script style overview of the content."""
        prompt = f"""{self._mode_prefix(mode)}

Create a video script overview of the provided sources.
Write it as if you're narrating an educational video.

Include:
- **Opening Hook** (grab attention)
- **Introduction** (what we'll cover)
- **Main Sections** (3-5 key segments with clear transitions)
- **Key Takeaways** (summary)
- **Closing** (call to action / next steps)

Use a conversational but informative tone. Include visual cues in [brackets] like [Show diagram] or [Cut to example].

SOURCES:
{knowledge_base[:35000]}"""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  QUIZ GENERATOR
    # ═══════════════════════════════════════════════════════════

    def generate_quiz(self, knowledge_base: str, num_questions: int = 10, mode: str = "Student Mode") -> list[dict]:
        """Generate MCQ quiz. Returns list of {question, options[], correct_answer, explanation}."""
        prompt = f"""{self._mode_prefix(mode)}

Create {num_questions} multiple choice quiz questions based on the provided sources.

Return ONLY a JSON array. Each item must have:
- "question": The question text
- "options": Array of exactly 4 answer choices (strings)
- "correct_answer": The correct option (exact text from options)
- "explanation": Brief explanation of why this is correct

Example:
[{{"question": "What is X?", "options": ["A", "B", "C", "D"], "correct_answer": "B", "explanation": "Because..."}}]

SOURCES:
{knowledge_base[:30000]}"""

        raw = self._generate(prompt)
        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return [{
                "question": "What is the main topic of the provided sources?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct_answer": "Option A",
                "explanation": "Review the sources for the correct answer."
            }]

    # ═══════════════════════════════════════════════════════════
    #  AUDIO OVERVIEW (script for TTS)
    # ═══════════════════════════════════════════════════════════

    def generate_audio_script(self, knowledge_base: str, mode: str = "Student Mode") -> str:
        """Generate an audio-friendly script for text-to-speech."""
        prompt = f"""{self._mode_prefix(mode)}

Write a clear, spoken-word audio script summarizing the provided sources.
This will be converted to speech, so:
- Use natural, conversational language
- Avoid visual formatting (no bullets, headers, etc.)
- Use transition phrases ("Now let's talk about...", "Moving on to...")
- Keep sentences medium length for easy listening
- Aim for 3-5 minutes of speaking time (about 600-900 words)

SOURCES:
{knowledge_base[:30000]}"""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  EXAM QUESTION PREDICTOR
    # ═══════════════════════════════════════════════════════════

    def predict_exam_questions(self, past_questions: str, source_content: str, mode: str = "Student Mode") -> list[dict]:
        """Analyze past exam questions and predict likely future questions.

        Returns list of {question, confidence, topic, reasoning}.
        """
        prompt = f"""{self._mode_prefix(mode)}
{CRITICAL_THINKING_INSTRUCTION}

You are an exam question predictor. Analyze these PREVIOUS YEAR QUESTIONS and the STUDY MATERIAL,
then predict 10 likely exam questions for the upcoming exam.

ANALYSIS APPROACH:
1. Identify recurring topics and patterns in past questions
2. Find important topics in the study material NOT yet covered by past questions
3. Consider question difficulty progression
4. Predict both direct and application-based questions

Return ONLY a JSON array. Each item must have:
- "question": The predicted question text
- "confidence": "High", "Medium", or "Low"
- "topic": The topic area
- "reasoning": Why you think this question is likely

PREVIOUS YEAR QUESTIONS:
{past_questions[:20000]}

STUDY MATERIAL:
{source_content[:20000]}"""

        raw = self._generate(prompt)
        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return [{
                "question": "Review past papers for patterns.",
                "confidence": "Medium",
                "topic": "General",
                "reasoning": "Based on recurring themes in past examinations."
            }]

    # ═══════════════════════════════════════════════════════════
    #  REVISION SUMMARY
    # ═══════════════════════════════════════════════════════════

    def generate_revision_summary(self, knowledge_base: str, mode: str = "Student Mode") -> str:
        """Generate a comprehensive revision summary of all content."""
        prompt = f"""{self._mode_prefix(mode)}
{CRITICAL_THINKING_INSTRUCTION}

Create a COMPREHENSIVE REVISION SUMMARY covering ALL topics from the provided sources.

Structure:
## Overview
Brief introduction to what's covered.

## Topic-by-Topic Revision
For each major topic:
### [Topic Name]
- **Key Concepts**: Core ideas to remember
- **Important Definitions**: Terms you must know
- **Formulas / Rules** (if applicable)
- **Common Mistakes**: What to watch out for
- **Quick Test**: 2-3 self-check questions

## Final Quick Reference
- Top 10 things to remember
- Mnemonics or memory aids
- Last-minute tips

Be thorough — this is the student's final revision before an exam.

SOURCES:
{knowledge_base[:50000]}"""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  ANSWER QUESTION (from question box)
    # ═══════════════════════════════════════════════════════════

    def answer_question(self, knowledge_base: str, question: str, mode: str = "Student Mode") -> str:
        """Answer a user's question based on uploaded content with critical thinking."""
        prompt = f"""{self._mode_prefix(mode)}
{CRITICAL_THINKING_INSTRUCTION}

You are StudyBuddy AI. Answer the following question based ONLY on the provided sources.

RULES:
1. Only use information from the sources. Never make up facts.
2. Cite sources with [Source: name].
3. Apply critical thinking — don't just summarize, analyze and explain.
4. Use markdown formatting.
5. If the sources don't cover this topic, say so honestly.

SOURCES:
{knowledge_base[:45000]}

QUESTION:
{question}"""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  TOPIC EXTRACTION (for YouTube recommendations)
    # ═══════════════════════════════════════════════════════════

    def extract_topics(self, knowledge_base: str) -> list[str]:
        """Extract main topics from sources for YouTube recommendations."""
        prompt = f"""Extract the 3-5 main topics from these sources.
Return ONLY a JSON array of short topic strings (2-4 words each).
Example: ["Machine Learning Basics", "Neural Networks", "Data Preprocessing"]

Sources:
{knowledge_base[:15000]}"""

        raw = self._generate(prompt)
        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)[:5]
        except (json.JSONDecodeError, IndexError):
            return ["study material"]

    # ═══════════════════════════════════════════════════════════
    #  SOURCE SUMMARY
    # ═══════════════════════════════════════════════════════════

    def summarize_source(self, source_text: str, source_name: str) -> str:
        """Generate a brief summary of a single source."""
        prompt = f"""Summarize this source in 2-3 concise sentences. Focus on the main topics covered.

Source: {source_name}
Content:
{source_text[:10000]}"""

        return self._generate(prompt)

    # ═══════════════════════════════════════════════════════════
    #  NOTEBOOK TITLE SUGGESTION
    # ═══════════════════════════════════════════════════════════

    def suggest_notebook_title(self, text: str) -> str:
        """Suggest a notebook title from source content."""
        prompt = (
            "Suggest a short, descriptive notebook title (5 words or fewer) for content about:\n\n"
            f"{text[:5000]}"
        )
        return self._generate(prompt).replace('"', '').replace("'", "").strip()

    # ═══════════════════════════════════════════════════════════
    #  SAVE TO NOTE
    # ═══════════════════════════════════════════════════════════

    def convert_to_note(self, content: str) -> tuple[str, str]:
        """Convert AI response to a note with title and cleaned content."""
        prompt = f"""Convert this text into a clean, well-formatted note.
Return a JSON object with exactly two keys: "title" (short, 5-8 words) and "content" (the cleaned note in markdown).

Text:
{content[:5000]}"""

        raw = self._generate(prompt)
        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw)
            return parsed.get("title", "Note"), parsed.get("content", content)
        except (json.JSONDecodeError, KeyError):
            lines = content.strip().split("\n")
            title = lines[0][:60].strip("#").strip() if lines else "Note"
            return title, content
