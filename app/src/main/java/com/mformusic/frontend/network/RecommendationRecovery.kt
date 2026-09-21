package com.mformusic.frontend.network

import java.io.IOException
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import retrofit2.Response

/** Only active recommendation reads retry; this is not a service keep-alive.
 * A two-minute total budget covers free-host startup without indefinite polling.
 */
object RecommendationRecovery {
    suspend fun <T> load(
        onWaiting: () -> Unit = {},
        pause: suspend (Long) -> Unit = { delay(it) },
        request: suspend () -> Response<T>
    ): Response<T> = withTimeoutOrNull(120_000L) {
        val delays = longArrayOf(5_000L, 10_000L, 20_000L, 30_000L)
        for (attempt in 0..delays.size) {
            try {
                val response = request()
                val temporary = response.code() in setOf(502, 503, 504) ||
                    response.headers()["X-Recommendation-Status"] == "unavailable"
                if (!temporary) return@withTimeoutOrNull response
            } catch (e: IOException) {
                // Network timeouts during startup are retryable; cancellation propagates.
            }
            if (attempt == delays.size) break
            onWaiting()
            pause(delays[attempt])
        }
        throw IOException("Recommendations are temporarily unavailable. Please retry shortly.")
    } ?: throw IOException("Recommendations are taking longer to start. Please retry shortly.")
}
