import { useCallback, useEffect, useRef, useState } from 'react';

const getFullscreenElement = () =>
  document.fullscreenElement || document.webkitFullscreenElement || null;

const requestElementFullscreen = (element) => {
  if (element.requestFullscreen) {
    return element.requestFullscreen();
  }
  if (element.webkitRequestFullscreen) {
    return element.webkitRequestFullscreen();
  }
  return Promise.reject(new Error('Fullscreen API is not available'));
};

/**
 * Requests fullscreen when an interview starts and reports exits via onFullscreenExit.
 *
 * Browsers do not allow JavaScript to block the Escape key's native fullscreen-exit
 * behavior. This hook can only detect and react to a fullscreen exit; it cannot
 * prevent the exit itself.
 */
export const useFullscreenEnforcement = ({ enabled = true, onFullscreenExit } = {}) => {
  const onExitRef = useRef(onFullscreenExit);
  const [isFullscreen, setIsFullscreen] = useState(() => Boolean(getFullscreenElement()));

  useEffect(() => {
    onExitRef.current = onFullscreenExit;
  }, [onFullscreenExit]);

  const reenterFullscreen = useCallback(async () => {
    if (getFullscreenElement()) return;
    try {
      await requestElementFullscreen(document.documentElement);
    } catch (err) {
      console.warn('Fullscreen request failed', err);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const handleChange = () => {
      const inFullscreen = Boolean(getFullscreenElement());
      setIsFullscreen(inFullscreen);
      if (!inFullscreen) {
        onExitRef.current?.();
      }
    };

    document.addEventListener('fullscreenchange', handleChange);
    document.addEventListener('webkitfullscreenchange', handleChange);

    if (!getFullscreenElement()) {
      reenterFullscreen();
    }

    return () => {
      document.removeEventListener('fullscreenchange', handleChange);
      document.removeEventListener('webkitfullscreenchange', handleChange);
    };
  }, [enabled, reenterFullscreen]);

  return { isFullscreen, reenterFullscreen };
};
