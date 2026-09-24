import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  answerLearningQuestion,
  answerLearningQuiz,
  answerLearningPractice,
  answerLearningRetest,
  getLearningState,
  BASE_URL,
  ContractError,
} from "./api";

// ---------------------------------------------------------------------------
// Deterministic response fixtures (AC-5)
// ---------------------------------------------------------------------------

const LEARNING_ANSWER_RESPONSE = {
  user_id: "demo-student",
  concept: "additive-versioning",
  is_correct: true,
  misconception: null,
  mastery_before: 0.32,
  mastery_after: 0.52,
  attempts: 1,
  correct_count: 1,
  next_review_at: null,
};

const LEARNING_QUIZ_ANSWER_RESPONSE = {
  user_id: "demo-student",
  concept: "provider-fallback-pattern",
  is_correct: true,
  selected_answer: "So a flaky LLM provider degrades",
  correct_answer: "So a flaky LLM provider degrades",
  mastery_before: 0.32,
  mastery_after: 0.52,
  attempts: 1,
  correct_count: 1,
  next_review_at: null,
};

const LEARNING_STATE_RESPONSE = {
  user_id: "demo-student",
  concept: "additive-versioning",
  mastery: 0.32,
  attempts: 0,
  correct_count: 0,
  last_misconception: null,
  next_review_at: null,
};

function mockOk(data: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => data,
  } as Response;
}

function mockError(status: number, code: string, message: string): Response {
  return {
    ok: false,
    status,
    json: async () => ({ error: { code, message } }),
  } as Response;
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("learning API helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // answerLearningQuestion (AC-1, AC-2, AC-3)
  // -------------------------------------------------------------------------

  describe("answerLearningQuestion", () => {
    it("sends credentials: include to the correct endpoint", async () => {
      const fetchSpy = vi
        .spyOn(globalThis, "fetch")
        .mockResolvedValueOnce(mockOk(LEARNING_ANSWER_RESPONSE));

      await answerLearningQuestion({
        concept: "additive-versioning",
        answer: "Adding a new optional field",
      });

      expect(fetchSpy).toHaveBeenCalledOnce();
      const [url, opts] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(`${BASE_URL}/api/v1/learning/answer`);
      expect(opts.credentials).toBe("include");
    });

    it("body does not contain user_id (AC-1, AC-3)", async () => {
      const fetchSpy = vi
        .spyOn(globalThis, "fetch")
        .mockResolvedValueOnce(mockOk(LEARNING_ANSWER_RESPONSE));

      // Caller passes user_id — helper must drop it from the body.
      await answerLearningQuestion({
        user_id: "attacker-id",
        concept: "additive-versioning",
        answer: "Adding a new optional field",
      });

      const [, opts] = fetchSpy.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(opts.body as string) as Record<string, unknown>;
      expect(body).not.toHaveProperty("user_id");
      expect(body.concept).toBe("additive-versioning");
      expect(body.answer).toBe("Adding a new optional field");
    });

    it("throws ContractError on non-ok response", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        mockError(401, "unauthorized", "missing or invalid session"),
      );

      await expect(
        answerLearningQuestion({ concept: "x", answer: "y" }),
      ).rejects.toBeInstanceOf(ContractError);
    });
  });

  // -------------------------------------------------------------------------
  // answerLearningQuiz (AC-1, AC-2, AC-3)
  // -------------------------------------------------------------------------

  describe("answerLearningQuiz", () => {
    it("sends credentials: include and targets quiz answer endpoint", async () => {
      const fetchSpy = vi
        .spyOn(globalThis, "fetch")
        .mockResolvedValueOnce(mockOk(LEARNING_QUIZ_ANSWER_RESPONSE));

      await answerLearningQuiz({
        concept: "provider-fallback-pattern",
        selected_answer: "So a flaky LLM provider degrades",
      });

      expect(fetchSpy).toHaveBeenCalledOnce();
      const [url, opts] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(`${BASE_URL}/api/v1/learning/quiz/answer`);
      expect(opts.credentials).toBe("include");
    });

    it("body does not contain user_id (AC-1, AC-3)", async () => {
      const fetchSpy = vi
        .spyOn(globalThis, "fetch")
        .mockResolvedValueOnce(mockOk(LEARNING_QUIZ_ANSWER_RESPONSE));

      await answerLearningQuiz({
        user_id: "attacker-id",
        concept: "provider-fallback-pattern",
        selected_answer: "So a flaky LLM provider degrades",
      });

      const [, opts] = fetchSpy.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(opts.body as string) as Record<string, unknown>;
      expect(body).not.toHaveProperty("user_id");
      expect(body.concept).toBe("provider-fallback-pattern");
      expect(body.selected_answer).toBe("So a flaky LLM provider degrades");
    });
  });

  // -------------------------------------------------------------------------
  // answerLearningPractice (AC-1, AC-2)
  // -------------------------------------------------------------------------

  describe("answerLearningPractice", () => {
    it("sends credentials: include and omits user_id", async () => {
      const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        mockOk({
          user_id: "demo-student",
          concept: "provider-fallback-pattern",
          is_correct: false,
          selected_answer: "wrong",
          correct_answer: "right",
          mastery_before: 0.32,
          mastery_after: 0.27,
          attempts: 1,
          correct_count: 0,
          next_review_at: null,
        }),
      );

      await answerLearningPractice({
        user_id: "ignored",
        concept: "provider-fallback-pattern",
        selected_answer: "wrong",
      });

      const [url, opts] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(`${BASE_URL}/api/v1/learning/quiz/practice`);
      expect(opts.credentials).toBe("include");
      const body = JSON.parse(opts.body as string) as Record<string, unknown>;
      expect(body).not.toHaveProperty("user_id");
    });
  });

  // -------------------------------------------------------------------------
  // answerLearningRetest (AC-1, AC-2)
  // -------------------------------------------------------------------------

  describe("answerLearningRetest", () => {
    it("sends credentials: include and omits user_id", async () => {
      const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
        mockOk({
          user_id: "demo-student",
          concept: "additive-versioning",
          is_correct: true,
          selected_answer: "Add the new field",
          correct_answer: "Add the new field",
          mastery_before: 0.32,
          mastery_after: 0.52,
          attempts: 1,
          correct_count: 1,
          next_review_at: null,
        }),
      );

      await answerLearningRetest({
        user_id: "ignored",
        concept: "additive-versioning",
        selected_answer: "Add the new field",
      });

      const [url, opts] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(`${BASE_URL}/api/v1/learning/quiz/retest`);
      expect(opts.credentials).toBe("include");
      const body = JSON.parse(opts.body as string) as Record<string, unknown>;
      expect(body).not.toHaveProperty("user_id");
    });
  });

  // -------------------------------------------------------------------------
  // getLearningState (AC-2) — does not include user_id in query string
  // -------------------------------------------------------------------------

  describe("getLearningState", () => {
    it("sends credentials: include and does not append user_id to query", async () => {
      const fetchSpy = vi
        .spyOn(globalThis, "fetch")
        .mockResolvedValueOnce(mockOk(LEARNING_STATE_RESPONSE));

      await getLearningState("additive-versioning");

      expect(fetchSpy).toHaveBeenCalledOnce();
      const [url, opts] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
      expect(url).toContain(`${BASE_URL}/api/v1/learning/state`);
      expect(url).toContain("concept=additive-versioning");
      expect(url).not.toContain("user_id");
      expect(opts?.credentials).toBe("include");
    });
  });
});
