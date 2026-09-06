import { INTERVIEW_STATUS } from '../types/interview';

// Mock responses for the interview demo
const MOCK_QUESTIONS = [
  { id: 1, text: "Tell me about a time you had to lead a project under tight deadlines." },
  { id: 2, text: "How do you handle disagreements with senior team members?" },
  { id: 3, text: "Describe a complex technical problem you solved recently." }
];

export const createSession = async (candidateId) => {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({ sessionId: 'mock-session-123', status: INTERVIEW_STATUS.NOT_STARTED });
    }, 500);
  });
};

export const startInterview = async (sessionId) => {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({ status: INTERVIEW_STATUS.IN_PROGRESS, firstQuestion: MOCK_QUESTIONS[0] });
    }, 800);
  });
};

export const endInterview = async (sessionId) => {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({ status: INTERVIEW_STATUS.COMPLETED });
    }, 500);
  });
};

export const getSession = async (sessionId) => {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        candidateName: "Alex Doe",
        role: "Senior Frontend Engineer",
        questions: MOCK_QUESTIONS
      });
    }, 300);
  });
};
