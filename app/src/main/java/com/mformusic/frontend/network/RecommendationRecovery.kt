package com.mformusic.frontend.network

import java.io.IOException
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import retrofit2.Response

/** Only active recommendation reads retry; this is not a service keep-alive.
 * A five-minute total budget covers sequential backend/ML startup, with bounded polling.
 */
object RecommendationRecovery {
    suspend fun <T> load(
        onWaiting: () -> Unit = {},
        pause: suspend (Long) -> Unit = { delay(it) },
        request: suspend () -> Response<T>
    ): Response<T> = withTimeoutOrNull(300_000L) {
        val delays = longArrayOf(5_000L, 10_000L, 20_000L, 30_000L, 45_000L, 60_000L, 60_000L, 60_000L)
        for (attempt in 0..delays.size) {
            var retryAfter = 0L
            try {
                val response = request()
                val temporary = response.code() in setOf(429, 502, 503, 504) ||
                    response.headers()["X-Recommendation-Status"] == "unavailable"
                if (!temporary) return@withTimeoutOrNull response
                retryAfter = retryAfterMillis(response.headers()["Retry-After"])
                response.errorBody()?.close()
            } catch (e: IOException) {
                // Network timeouts during startup are retryable; cancellation propagates.
            }
            if (attempt == delays.size) break
            onWaiting()
            pause(maxOf(delays[attempt], retryAfter))
        }
        throw IOException("Recommendations are temporarily unavailable. Please retry shortly.")
    } ?: throw IOException("Recommendations are taking longer to start. Please retry shortly.")
    internal fun retryAfterMillis(value: String?): Long {
        val seconds = value?.trim()?.toLongOrNull()
        if (seconds != null) return seconds.coerceIn(0L, 300L) * 1000L
        return try {
            val date = java.text.SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss zzz", java.util.Locale.US)
                .parse(value ?: return 0L) ?: return 0L
            (date.time - System.currentTimeMillis()).coerceIn(0L, 300_000L)
        } catch (_: Exception) { 0L }
    }
}
