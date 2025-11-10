import os
from datetime import datetime, timezone
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Utilities ----------

def today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()

# Simple built-in pool of GRE words and idioms to bootstrap daily challenges
GRE_POOL = [
    {
        "word": "aberration",
        "word_meaning": "a departure from what is normal or expected",
        "word_example": "A warm winter day in Alaska is an aberration.",
        "idiom": "break the ice",
        "idiom_meaning": "to relieve tension or get conversation going",
        "idiom_example": "He told a joke to break the ice at the meeting.",
    },
    {
        "word": "laconic",
        "word_meaning": "using very few words; concise",
        "word_example": "Her laconic reply suggested disinterest.",
        "idiom": "once in a blue moon",
        "idiom_meaning": "very rarely",
        "idiom_example": "We go out for a fancy dinner once in a blue moon.",
    },
    {
        "word": "pellucid",
        "word_meaning": "transparently clear; easily understood",
        "word_example": "The professor gave a pellucid explanation.",
        "idiom": "hit the books",
        "idiom_meaning": "to begin studying in earnest",
        "idiom_example": "I need to hit the books before finals.",
    },
]

# ---------- Models for requests ----------

class StoryCreate(BaseModel):
    date: str
    text: str

class PracticeSubmit(BaseModel):
    date: str
    answers: List[int]

# ---------- Health ----------

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "❌ Database not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# ---------- Challenge ----------

@app.get("/api/challenge/today")
def get_today_challenge():
    d = today_str()
    existing = get_documents("challenge", {"date": d}, limit=1)
    if existing:
        item = existing[0]
        item["_id"] = str(item.get("_id"))
        return item
    # generate a challenge from pool using day index
    idx = datetime.now(timezone.utc).timetuple().tm_yday % len(GRE_POOL)
    pick = GRE_POOL[idx]
    data = {
        "date": d,
        **pick,
    }
    _id = create_document("challenge", data)
    data["_id"] = _id
    # Add a timeline event for availability
    create_document("timelineevent", {
        "kind": "milestone",
        "title": f"Daily challenge ready: {pick['word']}",
        "detail": pick["idiom"],
        "ref_id": _id,
        "date": d,
    })
    return data

# ---------- Story & Feedback ----------

@app.post("/api/story")
def submit_story(payload: StoryCreate):
    # Basic analytics
    text = payload.text.strip()
    tokens = len([t for t in text.replace("\n", " ").split(" ") if t])
    unique_words = len(set(w.strip('.,!?;:"\'()').lower() for w in text.split()))

    # count hits from today's challenge
    challenge = get_today_challenge()
    gre_hits = 0
    if challenge:
        w = challenge.get("word", "").lower()
        idiom = challenge.get("idiom", "").lower()
        txt = text.lower()
        if w and w in txt:
            gre_hits += 1
        if idiom and idiom in txt:
            gre_hits += 1

    data = {
        "date": payload.date,
        "text": text,
        "tokens": tokens,
        "unique_words": unique_words,
        "gre_hits": gre_hits,
    }
    story_id = create_document("story", data)

    # Add timeline event
    create_document("timelineevent", {
        "kind": "story",
        "title": "Story submitted",
        "detail": f"{tokens} tokens, {unique_words} unique words",
        "ref_id": story_id,
        "date": payload.date,
    })

    return {"story_id": story_id, **data}

@app.post("/api/feedback/{story_id}")
def generate_feedback(story_id: str):
    # Fetch story
    from bson import ObjectId
    story_docs = list(db["story"].find({"_id": ObjectId(story_id)}))
    if not story_docs:
        raise HTTPException(status_code=404, detail="Story not found")
    story = story_docs[0]
    text = story.get("text", "")

    # Lightweight heuristic feedback
    sentences = [s.strip() for s in text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
    avg_len = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
    readability = "concise" if avg_len < 14 else "balanced" if avg_len < 22 else "wordy"

    strengths: List[str] = []
    suggestions: List[str] = []

    if story.get("gre_hits", 0) >= 1:
        strengths.append("Used today’s challenge items in context")
    else:
        suggestions.append("Try to incorporate the GRE word and idiom in your story")

    if avg_len < 12:
        strengths.append("Crisp sentence structure")
        suggestions.append("Consider adding detail to a few sentences")
    elif avg_len > 22:
        suggestions.append("Break long sentences into shorter ones for clarity")
    else:
        strengths.append("Good rhythm and flow")

    # "Best version" pass: trim spaces, title-case sentences lightly
    best_version = ". ".join(s.capitalize() for s in [s.strip() for s in text.split(".") if s.strip()])
    if text.endswith("."):
        best_version += "."

    score = min(100, 60 + story.get("gre_hits", 0) * 10 + (10 if readability == "balanced" else 0))

    feedback_doc = {
        "story_id": story_id,
        "readability": readability,
        "strengths": strengths,
        "suggestions": suggestions,
        "best_version": best_version,
        "score": int(score),
    }
    fid = create_document("feedback", feedback_doc)

    # timeline
    create_document("timelineevent", {
        "kind": "feedback",
        "title": f"Feedback score: {int(score)}",
        "detail": readability,
        "ref_id": fid,
        "date": story.get("date", today_str()),
    })

    return {"feedback_id": fid, **feedback_doc}

# ---------- Practice ----------

@app.get("/api/practice/quiz")
def get_quiz():
    ch = get_today_challenge()
    # Simple 5-question quiz: meanings and usage
    questions: List[Dict[str, Any]] = []

    # Q1 word meaning
    questions.append({
        "prompt": f"What is the meaning of '{ch['word']}'?",
        "choices": [
            ch["word_meaning"],
            "a type of musical notation",
            "complete agreement",
            "extreme scarcity",
        ],
        "answer": 0,
    })
    # Q2 idiom meaning
    questions.append({
        "prompt": f"What does the idiom '{ch['idiom']}' mean?",
        "choices": [
            ch["idiom_meaning"],
            "to delay unnecessarily",
            "to agree reluctantly",
            "to speak frankly",
        ],
        "answer": 0,
    })
    # Q3 usage true/false
    questions.append({
        "prompt": f"True or False: Using '{ch['word']}' means being extremely talkative.",
        "choices": ["True", "False"],
        "answer": 1,
    })
    # Q4 select best sentence
    questions.append({
        "prompt": f"Select the sentence that correctly uses '{ch['word']}'.",
        "choices": [
            f"Her {ch['word']} explanation made everything clearer.",
            "He aberration to the store quickly.",
            "They idiom the plan yesterday.",
            "The book was very once in a blue moon.",
        ],
        "answer": 0,
    })
    # Q5 identify idiom context
    questions.append({
        "prompt": f"Choose the best context to use the idiom '{ch['idiom']}'.",
        "choices": [
            "Starting a conversation in a quiet group",
            "Describing a scientific anomaly",
            "Talking about heavy rainfall",
            "Explaining a legal contract",
        ],
        "answer": 0,
    })

    return {"date": ch["date"], "questions": questions}

@app.post("/api/practice/submit")
def submit_quiz(payload: PracticeSubmit):
    # For validation, rebuild the quiz answers
    quiz = get_quiz()
    answers = payload.answers
    if len(answers) != len(quiz["questions"]):
        raise HTTPException(status_code=400, detail="Invalid number of answers")

    correct = 0
    breakdown = []
    for i, q in enumerate(quiz["questions"]):
        is_correct = int(answers[i]) == int(q["answer"])
        correct += 1 if is_correct else 0
        breakdown.append({
            "prompt": q["prompt"],
            "chosen": int(answers[i]),
            "correct": int(q["answer"]),
            "is_correct": is_correct,
        })

    total = len(quiz["questions"]) 
    result = {
        "date": payload.date,
        "correct": correct,
        "total": total,
        "breakdown": breakdown,
    }
    rid = create_document("practiceresult", result)

    create_document("timelineevent", {
        "kind": "practice",
        "title": f"Practice: {correct}/{total}",
        "detail": "Quiz completed",
        "ref_id": rid,
        "date": payload.date,
    })

    return {"result_id": rid, **result}

# ---------- Timeline ----------

@app.get("/api/timeline")
def get_timeline():
    docs = db["timelineevent"].find().sort("created_at", -1).limit(25)
    items = []
    for d in docs:
        d["_id"] = str(d["_id"])
        items.append(d)
    return {"items": items}

# ---------- Schemas endpoint (for viewer tools) ----------

@app.get("/schema")
def read_schemas():
    try:
        from schemas import Challenge, Story, Feedback, Timelineevent, Practiceresult
        def model_fields(model):
            return {name: str(field.annotation) for name, field in model.model_fields.items()}
        return {
            "challenge": model_fields(Challenge),
            "story": model_fields(Story),
            "feedback": model_fields(Feedback),
            "timelineevent": model_fields(Timelineevent),
            "practiceresult": model_fields(Practiceresult),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
