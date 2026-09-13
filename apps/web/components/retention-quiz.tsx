
"use client";

import { useEffect, useState } from "react";

import {
  answerLearningPractice,
  answerLearningQuiz,
  answerLearningRetest,
  ContractError,
  getLearningQuiz,
  getLearningRetest,
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
type PracticeAnswer = Awaited<ReturnType<typeof answerLearningPractice>>;
type RetestQuestion = Awaited<ReturnType<typeof getLearningRetest>>;
type RetestAnswer = Awaited<ReturnType<typeof answerLearningRetest>>;

type LearningStage = "quiz" | "practice" | "retest" | "complete";

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

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof ContractError ? err.message : fallback;
}

export default function RetentionQuiz() {
  const [questionIndex, setQuestionIndex] = useState(0);
  const [question, setQuestion] = useState<QuizQuestion | null>(null);
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null);
  const [result, setResult] = useState<QuizAnswer | null>(null);

  const [practiceSelectedAnswer, setPracticeSelectedAnswer] =
    useState<string | null>(null);
  const [practiceResult, setPracticeResult] =
    useState<PracticeAnswer | null>(null);

  const [retestQuestion, setRetestQuestion] =
    useState<RetestQuestion | null>(null);
  const [retestSelectedAnswer, setRetestSelectedAnswer] =
    useState<string | null>(null);
  const [retestResult, setRetestResult] =
    useState<RetestAnswer | null>(null);

  const [stage, setStage] = useState<LearningStage>("quiz");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [loadingRetest, setLoadingRetest] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [complete, setComplete] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const concept: QuizConcept = QUIZ_CONCEPTS[questionIndex];

  useEffect(() => {
    let cancelled = false;

    async function loadQuestion() {
      setLoading(true);
      setError(null);
      setQuestion(null);
      setSelectedAnswer(null);
      setResult(null);
      setPracticeSelectedAnswer(null);
      setPracticeResult(null);
      setRetestQuestion(null);
      setRetestSelectedAnswer(null);
      setRetestResult(null);
      setStage("quiz");

      try {
        const nextQuestion = await getLearningQuiz(concept);

        if (!cancelled) {
          setQuestion(nextQuestion);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            getErrorMessage(err, "Unable to load the quiz question."),
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
  }, [concept, reloadKey]);

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

      if (!answer.is_correct) {
        setStage("practice");
      }
    } catch (err) {
      setError(
        getErrorMessage(err, "Unable to submit your answer."),
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePracticeSubmit() {
    if (
      !practiceSelectedAnswer ||
      !result?.practice_choices ||
      submitting
    ) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const practiceAnswer = await answerLearningPractice({
        user_id: USER_ID,
        concept,
        selected_answer: practiceSelectedAnswer,
      });

      setPracticeResult(practiceAnswer);

      if (practiceAnswer.is_correct) {
        setLoadingRetest(true);

        try {
          const nextRetest = await getLearningRetest(concept);
          setRetestQuestion(nextRetest);
          setRetestSelectedAnswer(null);
        } catch (err) {
          setError(
            getErrorMessage(
              err,
              "Practice passed, but the retest could not be loaded.",
            ),
          );
        } finally {
          setLoadingRetest(false);
        }
      }
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          "Unable to submit the targeted practice answer.",
        ),
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRetestSubmit() {
    if (
      !retestSelectedAnswer ||
      !retestQuestion ||
      submitting
    ) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const answer = await answerLearningRetest({
        user_id: USER_ID,
        concept: retestQuestion.concept,
        selected_answer: retestSelectedAnswer,
      });

      setRetestResult(answer);

      if (answer.is_correct) {
        setComplete(true);
        setStage("complete");
      }
    } catch (err) {
      setError(
        getErrorMessage(err, "Unable to submit the retest answer."),
      );
    } finally {
      setSubmitting(false);
    }
  }

  function handleContinueToRetest() {
    if (!retestQuestion || loadingRetest) {
      return;
    }

    setStage("retest");
  }

//   function handleCorrectAnswerContinue() {
//     if (!result || !result.is_correct || submitting) {
//       return;
//     }

//     if (questionIndex >= QUIZ_CONCEPTS.length - 1) {
//       setComplete(true);
//       return;
//     }

//     setQuestionIndex((current) => current + 1);
//   }

  function handleNextAfterRetest() {
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
    setStage("quiz");
    setReloadKey((current) => current + 1);
  }

  function handleRetry() {
    setError(null);
    setReloadKey((current) => current + 1);
  }

  const completedQuestions =
    result?.is_correct || retestResult?.is_correct
      ? questionIndex + 1
      : questionIndex;

  const progressPercent =
    (completedQuestions / QUIZ_CONCEPTS.length) * 100;

  if (complete) {
    return (
      <section className="w-full max-w-5xl rounded-2xl border border-black/10 bg-white p-6 shadow-sm sm:p-8">
        <div className="mx-auto max-w-2xl text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-50 text-2xl text-green-600">
            ✓
          </div>

          <p className="mt-5 text-sm font-medium uppercase tracking-[0.16em] text-green-600">
            Retention loop complete
          </p>

          <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            You proved the concept survived retrieval.
          </h2>

          <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-black/60">
            The system detected a weak retrieval, taught the concept,
            gave you targeted practice, and then tested the concept
            again with a fresh question.
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
              {stage === "quiz"
                ? "Retention check"
                : stage === "practice"
                  ? "Adaptive teaching"
                  : "Retention retest"}
            </p>

            <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
              {stage === "quiz"
                ? "Can you still explain the decisions?"
                : stage === "practice"
                  ? "Let's reinforce the weak concept."
                  : "Can you retrieve it again?"}
            </h2>

            <p className="mt-2 max-w-2xl text-sm leading-6 text-black/60">
              {stage === "quiz"
                ? "First, retrieve the concept without looking at the explanation."
                : stage === "practice"
                  ? "Your answer revealed a retention gap. Read the explanation, then apply the idea in a targeted question."
                  : "This is a fresh question. A second successful retrieval is stronger evidence of retention."}
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
              onClick={handleRetry}
              className="mt-4 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-800 hover:bg-red-50"
            >
              Try again
            </button>
          </div>
        )}

        {!loading && !error && question && stage === "quiz" && (
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
                    <span className="font-medium">{choice}</span>
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
          </div>
        )}

        {result && stage === "practice" && (
          <div className="mt-8">
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
              <div className="flex items-start gap-3">
                <div className="text-xl">!</div>

                <div>
                  <p className="font-semibold">
                    Not quite — let&apos;s teach the concept.
                  </p>

                  <p className="mt-2 text-sm leading-6 text-black/70">
                    <span className="font-medium">
                      Correct answer:
                    </span>{" "}
                    {result.correct_answer}
                  </p>
                </div>
              </div>
            </div>

            {result.explanation && (
              <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/60 p-6">
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-indigo-700">
                  Why it matters
                </p>

                <p className="mt-3 text-sm leading-7 text-black/75">
                  {result.explanation}
                </p>
              </div>
            )}

            {result.practice_question &&
              result.practice_choices && (
                <div className="mt-6">
                  <p className="text-sm font-medium uppercase tracking-[0.14em] text-indigo-600">
                    Targeted practice
                  </p>

                  <h3 className="mt-3 max-w-3xl text-xl font-semibold leading-8 tracking-tight">
                    {result.practice_question}
                  </h3>

                  <div className="mt-5 grid gap-3">
                    {result.practice_choices.map((choice) => {
                      const isSelected =
                        practiceSelectedAnswer === choice;

                      return (
                        <button
                          key={choice}
                          type="button"
                          disabled={
                            practiceResult !== null ||
                            submitting
                          }
                          onClick={() =>
                            setPracticeSelectedAnswer(choice)
                          }
                          className={[
                            "w-full rounded-xl border p-4 text-left text-sm leading-6 transition",
                            practiceResult !== null
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

                  {!practiceResult && (
                    <button
                      type="button"
                      disabled={
                        !practiceSelectedAnswer || submitting
                      }
                      onClick={() => void handlePracticeSubmit()}
                      className="mt-6 rounded-lg bg-black px-5 py-2.5 text-sm font-medium text-white transition hover:bg-black/80 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {submitting
                        ? "Checking…"
                        : "Check practice answer"}
                    </button>
                  )}
                </div>
              )}

            {practiceResult && (
              <div className="mt-6">
                <div
                  className={[
                    "rounded-xl border p-5",
                    practiceResult.is_correct
                      ? "border-green-200 bg-green-50"
                      : "border-amber-200 bg-amber-50",
                  ].join(" ")}
                >
                  <p className="font-semibold">
                    {practiceResult.is_correct
                      ? "Practice correct — now let&apos;s retest."
                      : "Still shaky — review the explanation and try again."}
                  </p>

                  {!practiceResult.is_correct && (
                    <p className="mt-2 text-sm leading-6 text-black/70">
                      Correct answer:{" "}
                      <span className="font-medium">
                        {practiceResult.correct_answer}
                      </span>
                    </p>
                  )}
                </div>

                {practiceResult.is_correct && (
                  <div className="mt-6">
                    {loadingRetest ? (
                      <p className="text-sm text-black/60">
                        Preparing a fresh retest question…
                      </p>
                    ) : retestQuestion ? (
                      <button
                        type="button"
                        onClick={handleContinueToRetest}
                        className="rounded-lg bg-black px-5 py-2.5 text-sm font-medium text-white transition hover:bg-black/80"
                      >
                        Continue to retest
                      </button>
                    ) : null}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {stage === "retest" && retestQuestion && (
          <div className="mt-8">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-green-50 px-3 py-1 text-xs font-medium capitalize text-green-700">
                Fresh question
              </span>

              <span className="rounded-full bg-black/[0.04] px-3 py-1 text-xs font-medium text-black/60">
                Bloom level: {retestQuestion.bloom_level}
              </span>
            </div>

            <h3 className="mt-5 max-w-3xl text-xl font-semibold leading-8 tracking-tight">
              {retestQuestion.question}
            </h3>

            <div className="mt-6 grid gap-3">
              {retestQuestion.choices.map((choice) => {
                const isSelected =
                  retestSelectedAnswer === choice;

                return (
                  <button
                    key={choice}
                    type="button"
                    disabled={retestResult !== null || submitting}
                    onClick={() =>
                      setRetestSelectedAnswer(choice)
                    }
                    className={[
                      "w-full rounded-xl border p-4 text-left text-sm leading-6 transition",
                      retestResult !== null
                        ? "cursor-default"
                        : "hover:border-black/30 hover:bg-black/[0.02]",
                      isSelected
                        ? "border-indigo-600 bg-indigo-50 ring-1 ring-indigo-600"
                        : "border-black/10",
                    ].join(" ")}
                  >
                    <span className="font-medium">{choice}</span>
                  </button>
                );
              })}
            </div>

            {!retestResult && (
              <button
                type="button"
                disabled={!retestSelectedAnswer || submitting}
                onClick={() => void handleRetestSubmit()}
                className="mt-6 rounded-lg bg-black px-5 py-2.5 text-sm font-medium text-white transition hover:bg-black/80 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {submitting ? "Checking…" : "Submit retest"}
              </button>
            )}

            {retestResult && (
              <div className="mt-8">
                <div
                  className={[
                    "rounded-xl border p-5",
                    retestResult.is_correct
                      ? "border-green-200 bg-green-50"
                      : "border-amber-200 bg-amber-50",
                  ].join(" ")}
                >
                  <p className="font-semibold">
                    {retestResult.is_correct
                      ? "Retest passed — concept retained."
                      : "Retest missed — the concept needs more review."}
                  </p>

                  <p className="mt-2 text-sm leading-6 text-black/70">
                    Correct answer:{" "}
                    <span className="font-medium">
                      {retestResult.correct_answer}
                    </span>
                  </p>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <div className="rounded-xl border border-black/10 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-black/45">
                      Mastery
                    </p>

                    <p className="mt-1 text-lg font-semibold">
                      {formatMastery(retestResult.mastery_before)}
                      <span className="mx-1 text-black/30">
                        →
                      </span>
                      {formatMastery(retestResult.mastery_after)}
                    </p>
                  </div>

                  <div className="rounded-xl border border-black/10 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-black/45">
                      Attempts
                    </p>

                    <p className="mt-1 text-lg font-semibold">
                      {retestResult.attempts}
                    </p>
                  </div>

                  <div className="rounded-xl border border-black/10 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-black/45">
                      Next review
                    </p>

                    <p className="mt-1 text-lg font-semibold">
                      {formatReviewDate(
                        retestResult.next_review_at,
                      )}
                    </p>
                  </div>
                </div>

                {retestResult.is_correct && (
                  <button
                    type="button"
                    onClick={handleNextAfterRetest}
                    className="mt-6 rounded-lg bg-black px-5 py-2.5 text-sm font-medium text-white transition hover:bg-black/80"
                  >
                    {questionIndex === QUIZ_CONCEPTS.length - 1
                      ? "Finish retention check"
                      : "Next concept"}
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
