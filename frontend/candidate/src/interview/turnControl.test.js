import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  formatQuestionHeading,
  mockQuestionCountCompletesInterview,
  nextMicMuteState,
  shouldCallEndOnLiveKitDisconnect,
  shouldEndInterviewFromMicToggle,
} from './turnControl.js';

const MIC_STATE = {
  INACTIVE: 'INACTIVE',
  LISTENING: 'LISTENING',
  PROCESSING: 'PROCESSING',
  MUTED: 'MUTED',
};

describe('candidate interview turn control', () => {
  it('does not call /end on the third microphone interaction', () => {
    for (let interaction = 1; interaction <= 5; interaction += 1) {
      assert.equal(shouldEndInterviewFromMicToggle(interaction), false);
    }
  });

  it('does not complete the interview because the heading shows Question N of M', () => {
    assert.equal(formatQuestionHeading({ number: 6, total: 6 }), 'Question 6 of 6');
    assert.equal(mockQuestionCountCompletesInterview(6, 6), false);
    assert.equal(mockQuestionCountCompletesInterview(6, 5), false);
  });

  it('does not display a hardcoded Question 1 of 3 heading for the live interview', () => {
    assert.equal(formatQuestionHeading({ number: 1 }), 'Question 1');
    assert.notEqual(formatQuestionHeading({ number: 1 }), 'Question 1 of 3');
    assert.notEqual(formatQuestionHeading({}), 'Question 1 of 3');
    assert.equal(formatQuestionHeading({}), 'Current question');
  });

  it('treats the microphone button as mute/unmute only', () => {
    assert.equal(nextMicMuteState(MIC_STATE.LISTENING, MIC_STATE), MIC_STATE.MUTED);
    assert.equal(nextMicMuteState(MIC_STATE.MUTED, MIC_STATE), MIC_STATE.LISTENING);
    assert.equal(nextMicMuteState(MIC_STATE.INACTIVE, MIC_STATE), MIC_STATE.MUTED);
  });

  it('does not call /end on a disconnected reconnect flicker during startup', () => {
    assert.equal(
      shouldCallEndOnLiveKitDisconnect({
        connectionState: 'disconnected',
        disconnectReason: '',
        interviewStatus: 'IN_PROGRESS',
        hadLiveConnection: true,
        alreadyEnding: false,
      }),
      false,
    );
  });

  it('does not call /end while reconnecting', () => {
    assert.equal(
      shouldCallEndOnLiveKitDisconnect({
        connectionState: 'reconnecting',
        disconnectReason: '',
        interviewStatus: 'IN_PROGRESS',
        hadLiveConnection: true,
        alreadyEnding: false,
      }),
      false,
    );
  });

  it('does not delete the room on CLIENT_INITIATED disconnect during a live interview', () => {
    assert.equal(
      shouldCallEndOnLiveKitDisconnect({
        connectionState: 'disconnected',
        disconnectReason: 'CLIENT_INITIATED',
        interviewStatus: 'IN_PROGRESS',
        hadLiveConnection: true,
        alreadyEnding: false,
      }),
      false,
    );
  });

  it('still ends when LiveKit reports ROOM_DELETED', () => {
    const args = {
      connectionState: 'disconnected',
      interviewStatus: 'IN_PROGRESS',
      hadLiveConnection: true,
      alreadyEnding: false,
    };
    assert.equal(
      shouldCallEndOnLiveKitDisconnect({ ...args, disconnectReason: 'ROOM_DELETED' }),
      true,
    );
    assert.equal(
      shouldCallEndOnLiveKitDisconnect({ ...args, disconnectReason: 5 }),
      true,
    );
  });

  it('explicit End Interview is not gated behind a disconnect reason', () => {
    assert.equal(
      shouldCallEndOnLiveKitDisconnect({
        connectionState: 'connected',
        disconnectReason: '',
        interviewStatus: 'IN_PROGRESS',
        hadLiveConnection: true,
        alreadyEnding: false,
      }),
      false,
    );
    assert.equal(
      shouldCallEndOnLiveKitDisconnect({
        connectionState: 'disconnected',
        disconnectReason: 'ROOM_DELETED',
        interviewStatus: 'IN_PROGRESS',
        hadLiveConnection: true,
        alreadyEnding: true,
      }),
      false,
    );
  });

  it('frontend does not end or reset the interview from displayed question count', () => {
    const hookSource = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../hooks/useInterview.js'),
      'utf8',
    );
    assert.equal(hookSource.includes('mockQuestionCountCompletesInterview'), false);
    assert.equal(/currentQuestionNumber\s*===/.test(hookSource), false);
    assert.equal(/totalQuestions\s*===/.test(hookSource), false);
    assert.match(hookSource, /lastQuestionTextRef/);
    assert.match(hookSource, /question_turn_budget/);
  });

  it('does not hardcode an interview question count in the live interview UI', () => {
    const pageSource = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../pages/InterviewPage.jsx'),
      'utf8',
    );
    const hookSource = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '../hooks/useInterview.js'),
      'utf8',
    );
    assert.equal(pageSource.includes('Question 1 of 3'), false);
    assert.equal(pageSource.includes('3 questions'), false);
    assert.match(pageSource, /total=\{totalQuestions\}/);
    assert.match(hookSource, /question_turn_budget/);
    assert.equal(hookSource.includes('setTotalQuestions(3)'), false);
  });
});
