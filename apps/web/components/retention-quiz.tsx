"use client";

import { useEffect, useState } from "react";

import {
  answerLearningQuiz,
  ContractError,
  getLearningQuiz,
} from "@/lib/api";

const USER_ID = "demo-student";

const QUIZ_CONCEPTS = [
  "additive-versioning",
  "contract-first-design",
  "sse-vs-json-mode",
  "provider-fallback-pattern",
  "spaced-repetition-scheduling",
] as const;

type QuizConcept = (typeof QUIZ_CONCEPTS)[number];

type QuizQuestion = Awaited<ReturnType<typeof getLearningQuiz>>;
type QuizAnswer = Awaited<ReturnType<typeof answerLearningQuiz>>;

function formatReviewDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Scheduled";
  }

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function formatMastery(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export default function RetentionQuiz() {
  const [questionIndex, setQuestionIndex] = useState(0);
  const [question, setQuestion] = useState<QuizQuestion | null>(null);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(
    null,
  );
  const [result, setResult] = useState<QuizAnswer | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [complete, setComplete] = useState(false);

  const concept: QuizConcept = QUIZ_CONCEPTS[questionIndex];

  useEffect(() => {
    let cancelled = false;

    async function loadQuestion() {
      setLoading(true);
      setError(null);
      setQuestion(null);
      setSelectedAnswer(null);
      setResult(null);

      try {
        const nextQuestion = await getLearningQuiz(concept);

        if (!cancelled) {
          setQuestion(nextQuestion);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ContractError
              ? err.message
              : "Unable to load the quiz question.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadQuestion();

    return () => {
      cancelled = true;
    };
  }, [concept]);

  async function handleSubmit() {
    if (!selectedAnswer || !question || submitting) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const answer = await answerLearningQuiz({
        user_id: USER_ID,
        concept: question.concept,
        selected_answer: selectedAnswer,
      });

      setResult(answer);
    } catch (err) {
      setError(
        err instanceof ContractError
          ? err.message
          : "Unable to submit your answer.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function handleNext() {
    if (questionIndex >= QUIZ_CONCEPTS.length - 1) {
      setComplete(true);
      return;
    }

    setQuestionIndex((current) => current + 1);
  }

  function handleRestart() {
    setQuestionIndex(0);
    setComplete(false);
    setError(null);
  }

  const completedQuestions = result
    ? questionIndex + 1
    : questionIndex;

  const progressPercent =
    (completedQuestions / QUIZ_CONCEPTS.length) * 100;

  if (complete) {
    return (
      <section className="w-full max-w-5xl rounded-2xl border border-black/10 bg-white p-6 shadow-sm sm:p-8">
        <div className="mx-auto max-w-2xl text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-indigo-50 text-2xl text-indigo-600">
            ✓
          </div>

          <p className="mt-5 text-sm font-medium uppercase tracking-[0.16em] text-indigo-600">
            Retention check complete
          </p>

          <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            You tested what you actually retained.
          </h2>

          <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-black/60">
            Five questions covered the architecture decisions you
            have been working with: contracts, client compatibility,
            provider resilience, and spaced repetition.
          </p>

          <button
            type="button"
            onClick={handleRestart}
            className="mt-6 rounded-lg bg-black px-5 py-2.5 text-sm font-medium text-white transition hover:bg-black/80"
          >
            Retake retention check
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="w-full max-w-5xl">
      <div className="rounded-2xl border border-black/10 bg-white p-6 shadow-sm sm:p-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.16em] text-indigo-600">
              Retention check
            </p>

            <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
              Can you still explain the decisions?
            </h2>

            <p className="mt-2 max-w-2xl text-sm leading-6 text-black/60">
              These questions test whether you retained the software
              engineering techniques behind this project—not just
              whether you can recognize the code.
            </p>
          </div>

          <div className="shrink-0 rounded-lg bg-black/[0.04] px-3 py-2 text-sm font-medium text-black/70">
            {questionIndex + 1} of {QUIZ_CONCEPTS.length}
          </div>
        </div>

        <div className="mt-6 h-2 overflow-hidden rounded-full bg-black/[0.06]">
          <div
            className="h-full rounded-full bg-indigo-600 transition-all duration-300"
            style={{
              width: `${Math.min(progressPercent, 100)}%`,
            }}
          />
        </div>

        {loading && (
          <div className="mt-8 rounded-xl border border-black/10 p-6">
            <p className="text-sm text-black/60">
              Loading retention question…
            </p>
          </div>
        )}

        {error && (
          <div className="mt-8 rounded-xl border border-red-200 bg-red-50 p-5">
            <p className="text-sm font-medium text-red-800">
              Quiz error
            </p>

            <p className="mt-1 text-sm text-red-700">
              {error}
            </p>

            <button
              type="button"
              onClick={() => {
                setError(null);
                setQuestion(null);
                setLoading(true);
                setQuestionIndex((current) => current);
              }}
              className="mt-4 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-800 hover:bg-red-50"
            >
              Try again
            </button>
          </div>
        )}

        {!loading && !error && question && (
          <div className="mt-8">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium capitalize text-indigo-700">
                Bloom level: {question.bloom_level}
              </span>

              <span className="rounded-full bg-black/[0.04] px-3 py-1 text-xs font-medium text-black/60">
                {question.concept}
              </span>
            </div>

            <h3 className="mt-5 max-w-3xl text-xl font-semibold leading-8 tracking-tight">
              {question.question}
            </h3>

            <div className="mt-6 grid gap-3">
              {question.choices.map((choice) => {
                const isSelected = selectedAnswer === choice;

                return (
                  <button
                    key={choice}
                    type="button"
                    disabled={result !== null || submitting}
                    onClick={() => setSelectedAnswer(choice)}
                    className={[
                      "w-full rounded-xl border p-4 text-left text-sm leading-6 transition",
                      result !== null
                        ? "cursor-default"
                        : "hover:border-black/30 hover:bg-black/[0.02]",
                      isSelected
                        ? "border-indigo-600 bg-indigo-50 ring-1 ring-indigo-600"
                        : "border-black/10",
                    ].join(" ")}
                  >
                    <span className="font-medium">
                      {choice}
                    </span>
                  </button>
                );
              })}
            </div>

            {!result && (
              <button
                type="button"
                disabled={!selectedAnswer || submitting}
                onClick={() => void handleSubmit()}
                className="mt-6 rounded-lg bg-black px-5 py-2.5 text-sm font-medium text-white transition hover:bg-black/80 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {submitting ? "Checking…" : "Submit answer"}
              </button>
            )}

            {result && (
              <div className="mt-8">
                <div
                  className={[
                    "rounded-xl border p-5",
                    result.is_correct
                      ? "border-green-200 bg-green-50"
                      : "border-amber-200 bg-amber-50",
                  ].join(" ")}
                >
                  <div className="flex items-start gap-3">
                    <div className="text-xl">
                      {result.is_correct ? "✓" : "!"}
                    </div>

                    <div>
                      <p className="font-semibold">
                        {result.is_correct
                          ? "Correct"
                          : "Not quite"}
                      </p>

                      <p className="mt-1 text-sm leading-6 text-black/65">
                        {result.is_correct
                          ? "Good retention. You remembered the architectural reason."
                          : "This is a useful miss. The next step is to reinforce the concept."}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-xl border border-black/10 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-black/45">
                      Mastery
                    </p>

                    <p className="mt-1 text-lg font-semibold">
                      {formatMastery(result.mastery_before)}
                      <span className="mx-1 text-black/30">
                        →
                      </span>
                      {formatMastery(result.mastery_after)}
                    </p>
                  </div>

                  <div className="rounded-xl border border-black/10 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-black/45">
                      Attempts
                    </p>

                    <p className="mt-1 text-lg font-semibold">
                      {result.attempts}
                    </p>
                  </div>

                  <div className="rounded-xl border border-black/10 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-black/45">
                      Correct
                    </p>

                    <p className="mt-1 text-lg font-semibold">
                      {result.correct_count}
                    </p>
                  </div>

                  <div className="rounded-xl border border-black/10 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-black/45">
                      Next review
                    </p>

                    <p className="mt-1 text-lg font-semibold">
                      {formatReviewDate(result.next_review_at)}
                    </p>
                  </div>
                </div>

                <div className="mt-5">
                  <div className="flex items-center justify-between text-xs text-black/50">
                    <span>Current mastery</span>

                    <span>
                      {formatMastery(result.mastery_after)}
                    </span>
                  </div>

                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-black/[0.06]">
                    <div
                      className="h-full rounded-full bg-indigo-600 transition-all duration-500"
                      style={{
                        width: `${Math.round(
                          result.mastery_after * 100,
                        )}%`,
                      }}
                    />
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleNext}
                  className="mt-6 rounded-lg bg-black px-5 py-2.5 text-sm font-medium text-white transition hover:bg-black/80"
                >
                  {questionIndex === QUIZ_CONCEPTS.length - 1
                    ? "Finish retention check"
                    : "Next question"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}