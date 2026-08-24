package com.mformusic.frontend.telemetry

import android.util.Log
import com.mformusic.frontend.network.RetrofitClient
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel

object TelemetryRepository {

    private const val TAG = "TelemetryRepo"
    private const val CHANNEL_CAPACITY = 100
    private val channel = Channel<TelemetryEvent>(CHANNEL_CAPACITY)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var drainJob: Job? = null

    fun start() {
        if (drainJob?.isActive == true) return

        drainJob = scope.launch {
            for (event in channel) {
    Log.d("TELEMETRY_TEST", "🚀 Dispatched Event: type=${event.interactionType}, songId=${event.songId}, userId=${event.userId}, duration=${event.playDurationSec}s, completion=${event.completionRate}, session=${event.sessionId}")
    try {
        RetrofitClient.telemetryApiService.postInteraction(event)
    } catch (e: Exception) {
        Log.w(TAG, "Backend not reachable yet (expected until Phase 2): ${e.message}")
    }
}
        }
    }

    fun enqueue(event: TelemetryEvent) {
        channel.trySend(event)
    }

    fun stop() {
        drainJob?.cancel()
    }
}