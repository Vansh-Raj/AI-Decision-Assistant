import asyncio
import json
import os
import sys
from dotenv import load_dotenv

# Ensure the root directory is in the path so 'backend' module is found
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure env variables are loaded for LangSmith and OpenRouter
load_dotenv(override=True)

from langsmith import Client
from langsmith.evaluation import evaluate, LangChainStringEvaluator

from backend.app.rag.pipeline import RagPipeline
import backend.app.rag.pipeline

# A concise alternative prompt to test against the original
PROMPT_V2 = """You are a highly concise decision assistant. Answer the user's question directly using ONLY the provided context chunks.
Do not use conversational filler. Be extremely brief.
Respond in this exact XML structure:
<reasoning>Your reasoning here</reasoning>
<answer>Short and direct answer here.</answer>
<sources>[{"chunk_id": "...", "page": 1}]</sources>"""


async def run_pipeline_for_eval(question: str) -> str:
    pipeline = RagPipeline()
    answer = ""
    
    # Consume the streaming response to get the final answer
    async for event in pipeline.stream_rag_response(query=question):
        if event.startswith("data: "):
            payload = event[6:].strip()
            if payload == "[DONE]":
                continue
            try:
                data = json.loads(payload)
                if data.get("type") == "final":
                    answer = data.get("answer", "")
            except json.JSONDecodeError:
                pass
    return answer


async def predict_v1(inputs: dict) -> dict:
    # Uses the default SYSTEM_PROMPT
    answer = await run_pipeline_for_eval(inputs["question"])
    return {"output": answer}


async def predict_v2(inputs: dict) -> dict:
    # Temporarily monkey-patch the prompt
    original_prompt = backend.app.rag.pipeline.SYSTEM_PROMPT
    backend.app.rag.pipeline.SYSTEM_PROMPT = PROMPT_V2
    
    answer = await run_pipeline_for_eval(inputs["question"])
    
    # Restore original prompt
    backend.app.rag.pipeline.SYSTEM_PROMPT = original_prompt
    return {"output": answer}


def main():
    print("Connecting to LangSmith...")
    client = Client()
    dataset_name = "Assignment_RAG_Evaluation"
    
    # 1. Create or fetch a test dataset
    try:
        dataset = client.read_dataset(dataset_name=dataset_name)
        print(f"Found existing dataset: {dataset_name}")
    except Exception:
        print(f"Creating new dataset: {dataset_name}")
        dataset = client.create_dataset(dataset_name=dataset_name, description="Test questions for Prompt Evaluation Bonus")
        
        # Add sample questions. (Ideally, these would be based on uploaded docs!)
        examples = [
            ("Can you summarize the main objectives?", "The main objectives are..."),
            ("What are the risks mentioned in the document?", "The risks include..."),
        ]
        for q, a in examples:
            client.create_example(
                inputs={"question": q},
                outputs={"expected": a},
                dataset_id=dataset.id,
            )

    # 2. Define evaluators (Uses LLM-as-a-judge to score the answers)
    print("Setting up AI Judges (Faithfulness, Relevance, Groundedness)...")
    from backend.app.config import settings
    from langchain_openai import ChatOpenAI
    
    eval_llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0
    )
    
    # Relevance: Does the response answer the specific user question?
    relevance_eval = LangChainStringEvaluator("criteria", config={"criteria": "relevance", "llm": eval_llm})
    
    # Faithfulness (Helpfulness/Accuracy): Is the information accurate based on the context?
    faithfulness_eval = LangChainStringEvaluator("criteria", config={"criteria": "accuracy", "llm": eval_llm})
    
    # Groundedness: Is the response fully grounded in the provided document without hallucinating external info?
    groundedness_eval = LangChainStringEvaluator(
        "criteria", 
        config={"criteria": {"groundedness": "Does the submission ONLY contain information strictly present in the reference context?"}, "llm": eval_llm}
    )

    evaluators = [relevance_eval, faithfulness_eval, groundedness_eval]

    # 3. Run the evaluations!
    print("\n--- Evaluating Prompt V1 (Original / Detailed) ---")
    evaluate(
        predict_v1,
        data=dataset_name,
        evaluators=evaluators,
        experiment_prefix="Prompt_V1_Detailed",
    )

    print("\n--- Evaluating Prompt V2 (Concise) ---")
    evaluate(
        predict_v2,
        data=dataset_name,
        evaluators=evaluators,
        experiment_prefix="Prompt_V2_Concise",
    )
    
    print("\nDone! View the side-by-side prompt comparison in your LangSmith Dashboard.")


if __name__ == "__main__":
    main()
