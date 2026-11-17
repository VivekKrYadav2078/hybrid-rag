
import os
import json
import asyncio

from openai import OpenAI

from ragas.llms import llm_factory
from ragas.embeddings import HuggingFaceEmbeddings

from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision
)

# Existing RAG pipeline
from rag import (
    hybrid_search,
    rerank_chunks,
    build_rag_prompt,
    stream_groq_response
)

from config import GROQ_API_KEY
from db import supabase


# ==========================================
# CONFIGURATION
# ==========================================

os.environ["GROQ_API_KEY"] = GROQ_API_KEY

EVALUATION_MODEL = "openai/gpt-oss-120b"

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

DATASET_FILE = "eval_dataset.json"

OUTPUT_FILE = "ragas_evaluation_results.json"


# ==========================================
# 1. GET TENANT ID
# ==========================================

def get_tenant_id():

    res = (
        supabase
        .table("documents")
        .select("tenant_id")
        .limit(1)
        .execute()
    )

    if res.data:
        return res.data[0]["tenant_id"]

    raise ValueError(
        "No documents found in Supabase. "
        "Ingest at least one document first!"
    )


# ==========================================
# 2. RUN EXISTING RAG PIPELINE
# ==========================================

def run_rag_pipeline(tenant_id, question):

    # Hybrid search
    candidates = hybrid_search(
        tenant_id,
        question,
        top_k=15
    )

    # Reranking
    top_chunks = rerank_chunks(
        question,
        candidates,
        top_k=4
    )

    # Extract contexts
    retrieved_contexts = [
        chunk["content"]
        for chunk in top_chunks
    ]

    # Build prompt
    messages = build_rag_prompt(
        top_chunks,
        [],
        question
    )

    # Generate response
    response_stream = stream_groq_response(messages)

    generated_answer = "".join(
        chunk if isinstance(chunk, str) else chunk.content
        for chunk in response_stream
    )

    return retrieved_contexts, generated_answer


# ==========================================
# 3. INITIALIZE EVALUATION MODELS
# ==========================================

def initialize_evaluation_models():

    print("\nInitializing evaluation models...")

    # Groq using OpenAI-compatible API
    groq_client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )

    # Modern RAGAS LLM interface
    # Uses OpenAI adapter instead of Groq Instructor adapter
    eval_llm = llm_factory(
        model=EVALUATION_MODEL,
        client=groq_client
    )

    # Native RAGAS HuggingFace embeddings
    eval_embeddings = HuggingFaceEmbeddings(
        model=EMBEDDING_MODEL
    )

    print("Evaluation models initialized successfully!")

    return eval_llm, eval_embeddings


# ==========================================
# 4. INITIALIZE METRICS
# ==========================================

def initialize_metrics(eval_llm, eval_embeddings):

    metrics = {

        "faithfulness": Faithfulness(
            llm=eval_llm
        ),

        "answer_relevancy": AnswerRelevancy(
            llm=eval_llm,
            embeddings=eval_embeddings
        ),

        "context_precision": ContextPrecision(
            llm=eval_llm
        )

    }

    return metrics


# ==========================================
# 5. EVALUATE ONE SAMPLE
# ==========================================

async def evaluate_sample(sample, metrics):

    result = {
        **sample,
        "scores": {}
    }

    # Inputs required by individual metrics
    metric_inputs = {

        "faithfulness": {

            "user_input": sample["user_input"],

            "response": sample["response"],

            "retrieved_contexts": sample["retrieved_contexts"]

        },

        "answer_relevancy": {

            "user_input": sample["user_input"],

            "response": sample["response"]

        },

        "context_precision": {

            "user_input": sample["user_input"],

            "retrieved_contexts": sample["retrieved_contexts"],

            "reference": sample["reference"]

        }

    }

    for metric_name, metric in metrics.items():

        try:

            score = await metric.ascore(
                **metric_inputs[metric_name]
            )

            result["scores"][metric_name] = score.value

            print(
                f"  {metric_name}: {score.value:.4f}"
            )

        except Exception as e:

            print(
                f"  Error in {metric_name}: {e}"
            )

            result["scores"][metric_name] = None

    return result


# ==========================================
# 6. CALCULATE AVERAGE SCORES
# ==========================================

def calculate_average_scores(results):

    averages = {}

    metric_names = [
        "faithfulness",
        "answer_relevancy",
        "context_precision"
    ]

    for metric_name in metric_names:

        valid_scores = [

            item["scores"][metric_name]

            for item in results

            if item["scores"].get(metric_name) is not None

        ]

        if valid_scores:

            averages[metric_name] = (
                sum(valid_scores) / len(valid_scores)
            )

        else:

            averages[metric_name] = None

    return averages


# ==========================================
# 7. MAIN EVALUATION
# ==========================================

async def run_ragas_evaluation():

    # Get tenant
    tenant_id = get_tenant_id()

    print(f"\nUsing Tenant ID: {tenant_id}")

    # Load dataset
    print("\nLoading evaluation dataset...")

    with open(
        DATASET_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        eval_data = json.load(f)

    if not eval_data:

        raise ValueError(
            "Evaluation dataset is empty!"
        )

    # Execute RAG pipeline
    evaluation_samples = []

    print("\nExecuting RAG pipeline...\n")

    for index, item in enumerate(
        eval_data,
        start=1
    ):

        question = item["user_input"]

        reference = item["reference"]

        print(
            f"Processing {index}/{len(eval_data)}: {question}"
        )

        contexts, answer = run_rag_pipeline(
            tenant_id,
            question
        )

        evaluation_samples.append({

            "user_input": question,

            "retrieved_contexts": contexts,

            "response": answer,

            "reference": reference 

        })

        print(
            f"Retrieved chunks: {len(contexts)}"
        )

        print(
            f"Generated answer: {answer[:150]}...\n"
        )

    # Initialize models
    eval_llm, eval_embeddings = (
        initialize_evaluation_models()
    )

    # Initialize metrics
    metrics = initialize_metrics(
        eval_llm,
        eval_embeddings
    )

    # Evaluate
    print("\nRunning RAGAS evaluation...\n")

    results = []

    for index, sample in enumerate(
        evaluation_samples,
        start=1
    ):

        print(
            f"Evaluating sample {index}/{len(evaluation_samples)}"
        )

        result = await evaluate_sample(
            sample,
            metrics
        )

        results.append(result)

    # Calculate averages
    averages = calculate_average_scores(results)

    # Display results
    print("\n" + "=" * 55)

    print("RAGAS EVALUATION RESULTS")

    print("=" * 55)

    for metric_name, score in averages.items():

        if score is not None:

            print(
                f"{metric_name}: {score:.4f}"
            )

        else:

            print(
                f"{metric_name}: No valid scores"
            )

    # Save results
    output = {

        "tenant_id": str(tenant_id),

        "total_questions": len(results),

        "average_scores": averages,

        "results": results

    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=4,
            ensure_ascii=False
        )

    print("\n" + "=" * 55)

    print(
        f"Results saved to {OUTPUT_FILE}"
    )

    print("=" * 55)


# ==========================================
# 8. ENTRY POINT
# ==========================================

if __name__ == "__main__":

    asyncio.run(
        run_ragas_evaluation()
    )
