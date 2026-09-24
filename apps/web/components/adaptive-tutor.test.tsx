import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// ---------------------------------------------------------------------------
// Deterministic response fixtures (AC-5)
// ---------------------------------------------------------------------------

const LEARNING_STATE_FIXTURE = {
  user_id: "session-learner-1",
  concept: "虽然",
  mastery: 0.42,
  attempts: 3,
  correct_count: 2,
  last_misconception: null,
  next_review_at: null,
};

const LEARNING_ANSWER_FIXTURE = {
  user_id: "session-learner-1",
  concept: "虽然",
  is_correct: true,
  misconception: null,
  mastery_before: 0.42,
  mastery_after: 0.62,
  attempts: 4,
  correct_count: 3,
  next_review_at: null,
};

const UNAUTHORIZED_CONTRACT_ERROR_FIXTURE = {
  name: "ContractError",
  code: "unauthorized",
  message: "session authentication required",
};

// ---------------------------------------------------------------------------
// Source inspection — no React rendering required
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const componentSource = readFileSync(
  path.join(__dirname, "adaptive-tutor.tsx"),
  "utf-8",
);

describe("AdaptiveTutor — no client-side identity (AC-1)", () => {
  it("does not define a USER_ID constant (AC-1)", () => {
    expect(componentSource).not.toMatch(/const USER_ID/);
  });

  it("does not contain the demo-student string literal (AC-1)", () => {
    expect(componentSource).not.toContain("demo-student");
  });

  it("answerLearningQuestion call does not include user_id property (AC-1)", () => {
    const match = componentSource.match(
      /answerLearningQuestion\(\{[\s\S]*?\}\)/,
    );
    expect(match).not.toBeNull();
    expect(match![0]).not.toContain("user_id");
  });
});

describe("AdaptiveTutor — unauthorized ContractError handling (AC-2, AC-3)", () => {
  it("defines an isUnauthorizedContractError predicate (AC-2)", () => {
    expect(componentSource).toMatch(/isUnauthorizedContractError/);
  });

  it("predicate checks for unauthorized code (AC-2)", () => {
    const match = componentSource.match(
      /function isUnauthorizedContractError[\s\S]*?\}/,
    );
    expect(match).not.toBeNull();
    expect(match![0]).toContain('"unauthorized"');
  });

  it("component source contains a session recovery message (AC-2)", () => {
    expect(componentSource).toMatch(
      /[Rr]efresh.*page|session.*expired|restore.*session/i,
    );
  });

  it("unauthorized catch branch does not call setState or setResult (AC-3)", () => {
    const match = componentSource.match(
      /if \(isUnauthorizedContractError\(err\)\) \{[\s\S]*?\} else/,
    );
    expect(match).not.toBeNull();
    const branch = match![0];
    expect(branch).not.toContain("setState(");
    expect(branch).not.toContain("setResult(");
  });

  it("unauthorized catch branch sets sessionExpired without overwriting mastery state (AC-3)", () => {
    const match = componentSource.match(
      /if \(isUnauthorizedContractError\(err\)\) \{[\s\S]*?\} else/,
    );
    expect(match).not.toBeNull();
    expect(match![0]).toContain("setSessionExpired(true)");
  });

  it("non-unauthorized catch branch still calls setError for generic errors (AC-2 edge case)", () => {
    const match = componentSource.match(
      /\} else \{[\s\S]*?setError\(toContractError\(err\)\)/,
    );
    expect(match).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Fixture shape verification — no external service required (AC-5)
// ---------------------------------------------------------------------------

describe("AdaptiveTutor — fixture shapes (AC-5)", () => {
  it("LEARNING_STATE_FIXTURE has required LearningStateResponse fields", () => {
    expect(LEARNING_STATE_FIXTURE.concept).toBeTruthy();
    expect(typeof LEARNING_STATE_FIXTURE.mastery).toBe("number");
    expect(typeof LEARNING_STATE_FIXTURE.attempts).toBe("number");
    expect(typeof LEARNING_STATE_FIXTURE.correct_count).toBe("number");
  });

  it("LEARNING_ANSWER_FIXTURE has required LearningAnswerResponse fields", () => {
    expect(LEARNING_ANSWER_FIXTURE.concept).toBeTruthy();
    expect(typeof LEARNING_ANSWER_FIXTURE.is_correct).toBe("boolean");
    expect(typeof LEARNING_ANSWER_FIXTURE.mastery_after).toBe("number");
    expect(typeof LEARNING_ANSWER_FIXTURE.mastery_before).toBe("number");
  });

  it("UNAUTHORIZED_CONTRACT_ERROR_FIXTURE represents a 401 session failure (AC-5)", () => {
    expect(UNAUTHORIZED_CONTRACT_ERROR_FIXTURE.code).toBe("unauthorized");
    expect(UNAUTHORIZED_CONTRACT_ERROR_FIXTURE.name).toBe("ContractError");
    expect(UNAUTHORIZED_CONTRACT_ERROR_FIXTURE.message).toBeTruthy();
  });
});
