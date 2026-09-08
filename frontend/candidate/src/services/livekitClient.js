import { Room, RoomEvent, Track } from 'livekit-client';

export class LiveKitSession {
  constructor() {
    this.room = new Room({
      adaptiveStream: true,
      dynacast: true,
    });

    this._onRemoteAudioTrack = null;
    this._onConnectionStateChange = null;
    this._onDisconnected = null;

    this.room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind !== Track.Kind.Audio) return;
      this._onRemoteAudioTrack?.(track.mediaStreamTrack);
    });

    this.room.on(RoomEvent.ConnectionStateChanged, (state) => {
      this._onConnectionStateChange?.(state);
    });

    this.room.on(RoomEvent.Disconnected, () => {
      this._onDisconnected?.();
    });
  }

  async connect(livekitUrl, token) {
    await this.room.connect(livekitUrl, token);
    await this.room.localParticipant.setMicrophoneEnabled(true);
  }

  async disconnect() {
    const participant = this.room.localParticipant;
    const tracks = [...participant.trackPublications.values()]
      .map((publication) => publication.track)
      .filter(Boolean);

    await Promise.all(
      tracks.map((track) => participant.unpublishTrack(track)),
    );

    await this.room.disconnect();
  }

  onRemoteAudioTrack(callback) {
    this._onRemoteAudioTrack = callback;
  }

  onConnectionStateChange(callback) {
    this._onConnectionStateChange = callback;
  }

  onDisconnected(callback) {
    this._onDisconnected = callback;
  }
}
