/**
 * Pure interview-turn helpers. The real interview is driven by the
 * LiveKit / backend session, not a local mock question list.
 */

const DISCONNECT_REASON_NAMES = {
  0: 'UNKNOWN_REASON',
  1: 'CLIENT_INITIATED',
  2: 'DUPLICATE_IDENTITY',
  3: 'SERVER_SHUTDOWN',
  4: 'PARTICIPANT_REMOVED',
  5: 'ROOM_DELETED',
  6: 'STATE_MISMATCH',
  7: 'JOIN_FAILURE',
};

export function shouldEndInterviewFromMicToggle(_interactionCount) {
  return false;
}

export function normalizeLiveKitDisconnectReason(reason) {
  if (reason == null || reason === '') return '';
  if (typeof reason === 'number') {
    return DISCONNECT_REASON_NAMES[reason] || String(reason);
  }
  const asString = String(reason);
  if (/^\d+$/.test(asString)) {
    return DISCONNECT_REASON_NAMES[Number(asString)] || asString;
  }
  return asString;
}

export function isRoomDeletedDisconnect(reason) {
  const name = normalizeLiveKitDisconnectReason(reason);
  return name === 'ROOM_DELETED';
}

export function shouldCallEndOnLiveKitDisconnect({
  connectionState,
  disconnectReason,
  interviewStatus,
  hadLiveConnection,
  alreadyEnding,
} = {}) {
  if (alreadyEnding) return false;
  if (!hadLiveConnection) return false;
  if (interviewStatus !== 'IN_PROGRESS') return false;
  if (connectionState !== 'disconnected') return false;
  return isRoomDeletedDisconnect(disconnectReason);
}

export function mockQuestionCountCompletesInterview(_mockLength, _questionIndex) {
  return false;
}

export function nextMicMuteState(state, micState) {
  if (state === micState.MUTED) return micState.LISTENING;
  return micState.MUTED;
}

export function formatQuestionHeading({ number, total } = {}) {
  if (number && total) return `Question ${number} of ${total}`;
  if (number) return `Question ${number}`;
  return 'Current question';
}
