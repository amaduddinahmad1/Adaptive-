import { useCallback, useEffect, useRef, useState } from 'react';

const MAX_VIOLATIONS = 3;

const warningForCount = (count) => {
  if (count === 1) {
    return 'Warning 1 of 3: please remain on this tab and in fullscreen for the duration of the interview.';
  }
  if (count === 2) {
    return 'Warning 2 of 3: please stay on this tab and in fullscreen. One more interruption will end the interview.';
  }
  return null;
};

/**
 * Tracks tab-switch and fullscreen-exit violations while an interview is in progress.
 * Warnings are shown for the first two events; the third ends the interview.
 */
export const useViolationTracking = ({ enabled = false } = {}) => {
  const [violations, setViolations] = useState([]);
  const [currentWarning, setCurrentWarning] = useState(null);
  const [interviewTerminated, setInterviewTerminated] = useState(false);

  const countRef = useRef(0);
  const terminatedRef = useRef(false);
  const enabledRef = useRef(enabled);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  const recordViolation = useCallback((type) => {
    if (!enabledRef.current || terminatedRef.current) return;

    countRef.current += 1;
    const count = countRef.current;
    const entry = {
      type,
      timestamp: new Date().toISOString(),
      count_at_time: count,
    };

    setViolations((prev) => [...prev, entry]);

    if (count >= MAX_VIOLATIONS) {
      terminatedRef.current = true;
      setInterviewTerminated(true);
      setCurrentWarning(null);
      return;
    }

    setCurrentWarning(warningForCount(count));
  }, []);

  const dismissWarning = useCallback(() => {
    setCurrentWarning(null);
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const handleVisibility = () => {
      if (document.hidden) {
        recordViolation('tab_switch');
      }
    };

    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [enabled, recordViolation]);

  return {
    violations,
    currentWarning,
    interviewTerminated,
    recordViolation,
    dismissWarning,
  };
};
