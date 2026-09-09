// adaptive-tutor.tsx

"use client";

// import { useEffect, useMemo, useState } from "react";
import { useMemo, useState } from "react";
import {
  answerLearningQuestion,
  // getLearningState,
  type ContractError,
} from "@/lib/api";
import type { components } from "@ai-fullstack-starter/api-contract";

type LearningState =
  components["schemas"]["LearningStateResponse"];

type LearningAnswerResponse =
  components["schemas"]["LearningAnswerResponse"];

const USER_ID = "demo-student";
const CONCEPT = "虽然";

const choices = [
  {
    value: "because",
    label: "because",
  },
  {
    value: "although",
    label: "although / even though",
  },
  {
    value: "therefore",
    label: "therefore",
  },
];

function percent(value: number) {
  return Math.round(value * 100);
}

function formatReviewDate(value: string | null) {
  if (!value) return "Not scheduled";

  const date = new Date(value);
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function toContractError(err: unknown): ContractError {
  if (err instanceof Error && "code" in err) {
    return err as ContractError;
  }

  return {
    name: "ContractError",
    message: err instanceof Error ? err.message : "Unable to complete request",
    code: "internal_error",
  } as ContractError;
}

export default function AdaptiveTutor() {
  const [state, setState] = useState<LearningState | null>(null);
  const [result, setResult] = useState<LearningAnswerResponse | null>(null);
  // const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ContractError | null>(null);

  // async function loadState() {
  //   try {
  //     setError(null);
  //     const learningState = await getLearningState(USER_ID, CONCEPT);
  //     setState(learningState);
  //   } catch (err) {
  //     setError(
  //       err instanceof Error
  //         ? (err as ContractError)
  //         : new Error("Unable to load learning state"),
  //     );
  //   }
  // }

  // useEffect(() => {
  //   void loadState();
  // }, []);

  const mastery = result?.mastery_after ?? state?.mastery ?? 0.32;

  const accuracy = useMemo(() => {
    if (!state || state.attempts === 0) return 0;
    return Math.round((state.correct_count / state.attempts) * 100);
  }, [state]);

  async function submitAnswer(answer: string) {
    // setSelected(answer);
    setLoading(true);
    setError(null);

    try {
      const response = await answerLearningQuestion({
        user_id: USER_ID,
        concept: CONCEPT,
        answer,
      });

      setResult(response);

      setState({
        user_id: response.user_id,
        concept: response.concept,
        mastery: response.mastery_after,
        attempts: response.attempts,
        correct_count: response.correct_count,
        last_misconception: response.misconception,
        next_review_at: response.next_review_at,
      });
    } catch (err) {
      // setError(
      //   err instanceof Error
      //     ? (err as ContractError)
      //     : new Error("Unable to submit answer"),
      // );
      // setError(
      //   err instanceof Error && "code" in err
      //     ? (err as ContractError)
      //     : new Error("Unable to submit answer") as ContractError,
      // );
      setError(toContractError(err));
    } finally {
      setLoading(false);
    }
  }

  function retry() {
    // setSelected(null);
    setResult(null);
    setError(null);
  }

  return (
    <section className="w-full max-w-5xl">
      <div className="overflow-hidden rounded-3xl border border-black/10 bg-white shadow-sm">
        <div className="border-b border-black/10 px-6 py-7 sm:px-8">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="mb-2 text-sm font-medium uppercase tracking-[0.16em] text-indigo-600">
                Adaptive Mandarin Tutor
              </p>
              <h2 className="text-3xl font-semibold tracking-tight">
                虽然
              </h2>
              <p className="mt-1 text-lg text-black/60">
                although / even though
              </p>
            </div>

            <div className="min-w-44">
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="font-medium">Your mastery</span>
                <span className="font-semibold">{percent(mastery)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-black/10">
                <div
                  className="h-full rounded-full bg-indigo-600 transition-all duration-500"
                  style={{ width: `${percent(mastery)}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[1fr_280px]">
          <div>
            <p className="text-sm font-medium text-black/50">
              Question
            </p>

            <h3 className="mt-2 text-xl font-semibold">
              Which meaning best matches 虽然?
            </h3>

            {!result && (
              <div className="mt-6 grid gap-3">
                {choices.map((choice) => (
                  <button
                    key={choice.value}
                    type="button"
                    disabled={loading}
                    onClick={() => void submitAnswer(choice.value)}
                    className="rounded-2xl border border-black/10 px-5 py-4 text-left font-medium transition hover:border-indigo-400 hover:bg-indigo-50 disabled:cursor-wait disabled:opacity-60"
                  >
                    {choice.label}
                  </button>
                ))}
              </div>
            )}

            {result && (
              <div className="mt-6">
                <div
                  className={`rounded-2xl border p-5 ${
                    result.is_correct
                      ? "border-emerald-200 bg-emerald-50"
                      : "border-amber-200 bg-amber-50"
                  }`}
                >
                  <p className="text-lg font-semibold">
                    {result.is_correct
                      ? "✓ Correct"
                      : "✗ Not quite"}
                  </p>

                  {!result.is_correct && result.misconception && (
                    <>
                      <p className="mt-2 font-medium">
                        You confused 虽然 with 因为.
                      </p>
                      <div className="mt-4 grid gap-2 text-sm">
                        <div>
                          <span className="font-semibold">虽然</span>
                          {" = "}although / even though
                        </div>
                        <div>
                          <span className="font-semibold">因为</span>
                          {" = "}because
                        </div>
                      </div>
                    </>
                  )}

                  {result.is_correct && (
                    <p className="mt-2 text-black/70">
                      Nice recovery. The tutor updated your mastery
                      based on this answer.
                    </p>
                  )}

                  <div className="mt-5 flex flex-wrap gap-3 text-sm">
                    <span className="rounded-full bg-white/80 px-3 py-1.5 font-medium">
                      Mastery: {percent(result.mastery_before)}% →{" "}
                      {percent(result.mastery_after)}%
                    </span>
                    <span className="rounded-full bg-white/80 px-3 py-1.5 font-medium">
                      Review: {formatReviewDate(result.next_review_at)}
                    </span>
                  </div>
                </div>

                {!result.is_correct && (
                  <button
                    type="button"
                    onClick={retry}
                    className="mt-4 rounded-xl bg-black px-5 py-3 font-medium text-white transition hover:bg-black/80"
                  >
                    Try again
                  </button>
                )}
              </div>
            )}

            {error && (
              <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                {error.message}
              </div>
            )}
          </div>

          <aside className="rounded-2xl bg-black/[0.035] p-5">
            <p className="text-sm font-semibold">Learning memory</p>

            <div className="mt-5 space-y-4 text-sm">
              <div className="flex justify-between gap-4">
                <span className="text-black/50">Concept</span>
                <span className="font-medium">虽然</span>
              </div>

              <div className="flex justify-between gap-4">
                <span className="text-black/50">Mastery</span>
                <span className="font-medium">{percent(mastery)}%</span>
              </div>

              <div className="flex justify-between gap-4">
                <span className="text-black/50">Attempts</span>
                <span className="font-medium">
                  {state?.attempts ?? 0}
                </span>
              </div>

              <div className="flex justify-between gap-4">
                <span className="text-black/50">Accuracy</span>
                <span className="font-medium">{accuracy}%</span>
              </div>

              <div>
                <p className="text-black/50">Last misconception</p>
                <p className="mt-1 font-medium">
                  {state?.last_misconception ?? "None yet"}
                </p>
              </div>

              <div>
                <p className="text-black/50">Next review</p>
                <p className="mt-1 font-medium">
                  {formatReviewDate(state?.next_review_at ?? null)}
                </p>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}