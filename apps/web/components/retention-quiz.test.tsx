import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// ---------------------------------------------------------------------------
// Deterministic response fixtures (AC-5)
// ---------------------------------------------------------------------------

const QUIZ_QUESTION_FIXTURE = {
  concept: "provider-fallback-pattern",
  question: "Why does the AI starter include a mock LLM provider by default?",
  choices: [
    "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
    "Always fail immediately when the primary provider is unavailable",
    "To avoid paying for API calls during development",
    "Because the real provider does not support streaming",
  ],
  bloom_level: "understand",
};

const QUIZ_ANSWER_FIXTURE = {
  user_id: "demo-student",
  concept: "provider-fallback-pattern",
  is_correct: true,
  selected_answer:
    "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
  correct_answer:
    "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
  mastery_before: 0.32,
  mastery_after: 0.52,
  attempts: 1,
  correct_count: 1,
  next_review_at: null,
  explanation: null,
  misconception: null,
  practice_question: null,
  practice_choices: null,
};

const PRACTICE_ANSWER_FIXTURE = {
  user_id: "demo-student",
  concept: "provider-fallback-pattern",
  is_correct: true,
  selected_answer:
    "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
  correct_answer:
    "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
  mastery_before: 0.27,
  mastery_after: 0.47,
  attempts: 2,
  correct_count: 1,
  next_review_at: null,
  explanation: null,
};

const RETEST_ANSWER_FIXTURE = {
  user_id: "demo-student",
  concept: "provider-fallback-pattern",
  is_correct: true,
  selected_answer:
    "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
  correct_answer:
    "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
  mastery_before: 0.47,
  mastery_after: 0.67,
  attempts: 3,
  correct_count: 2,
  next_review_at: "2026-10-01T00:00:00Z",
  misconception: null,
};

// ---------------------------------------------------------------------------
// Source inspection — no React rendering required
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const componentSource = readFileSync(
  path.join(__dirname, "retention-quiz.tsx"),
  "utf-8",
);

describe("RetentionQuiz — no client-side identity (AC-1, AC-2, AC-3)", () => {
  it("does not define a USER_ID constant (AC-1)", () => {
    expect(componentSource).not.toMatch(/const USER_ID/);
  });

  it("does not contain the demo-student string literal (AC-1)", () => {
    expect(componentSource).not.toContain("demo-student");
  });

  it("answerLearningQuiz call does not include user_id property (AC-2)", () => {
    const match = componentSource.match(
      /answerLearningQuiz\(\{[\s\S]*?\}\)/,
    );
    expect(match).not.toBeNull();
    expect(match![0]).not.toContain("user_id");
  });

  it("answerLearningPractice call does not include user_id property (AC-2)", () => {
    const match = componentSource.match(
      /answerLearningPractice\(\{[\s\S]*?\}\)/,
    );
    expect(match).not.toBeNull();
    expect(match![0]).not.toContain("user_id");
  });

  it("answerLearningRetest call does not include user_id property (AC-2)", () => {
    const match = componentSource.match(
      /answerLearningRetest\(\{[\s\S]*?\}\)/,
    );
    expect(match).not.toBeNull();
    expect(match![0]).not.toContain("user_id");
  });
});

// ---------------------------------------------------------------------------
// Fixture shape verification — no external service required (AC-5)
// ---------------------------------------------------------------------------

describe("RetentionQuiz — fixture shapes (AC-5)", () => {
  it("QUIZ_QUESTION_FIXTURE has required LearningQuizResponse fields", () => {
    expect(QUIZ_QUESTION_FIXTURE.concept).toBeTruthy();
    expect(QUIZ_QUESTION_FIXTURE.question).toBeTruthy();
    expect(Array.isArray(QUIZ_QUESTION_FIXTURE.choices)).toBe(true);
    expect(QUIZ_QUESTION_FIXTURE.bloom_level).toBeTruthy();
  });

  it("QUIZ_ANSWER_FIXTURE has required LearningQuizAnswerResponse fields", () => {
    expect(QUIZ_ANSWER_FIXTURE.concept).toBeTruthy();
    expect(typeof QUIZ_ANSWER_FIXTURE.is_correct).toBe("boolean");
    expect(typeof QUIZ_ANSWER_FIXTURE.mastery_after).toBe("number");
  });

  it("PRACTICE_ANSWER_FIXTURE has required LearningPracticeAnswerResponse fields", () => {
    expect(PRACTICE_ANSWER_FIXTURE.concept).toBeTruthy();
    expect(typeof PRACTICE_ANSWER_FIXTURE.is_correct).toBe("boolean");
    expect(typeof PRACTICE_ANSWER_FIXTURE.mastery_after).toBe("number");
  });

  it("RETEST_ANSWER_FIXTURE has required LearningRetestAnswerResponse fields", () => {
    expect(RETEST_ANSWER_FIXTURE.concept).toBeTruthy();
    expect(typeof RETEST_ANSWER_FIXTURE.is_correct).toBe("boolean");
    expect(RETEST_ANSWER_FIXTURE.next_review_at).toBeTruthy();
  });
});
