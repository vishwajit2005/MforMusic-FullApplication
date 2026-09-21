package com.mformusic.frontend.network

import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import okhttp3.Headers
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.*
import org.junit.Test
import retrofit2.Response

class RecommendationRecoveryTest {
    @Test fun outageThenRecoveryReturnsSongs() = runBlocking {
        var calls = 0
        val waits = mutableListOf<Long>()
        val result = RecommendationRecovery.load(pause = { waits.add(it) }) {
            calls++
            if (calls == 1) Response.success(emptyList<String>(), Headers.headersOf("X-Recommendation-Status", "unavailable"))
            else Response.success(listOf("song"))
        }
        assertEquals(listOf("song"), result.body())
        assertEquals(listOf(5000L), waits)
    }
    @Test fun genuineEmptyResponseDoesNotRetry() = runBlocking {
        val result = RecommendationRecovery.load(pause = { fail("Unexpected retry") }) {
            Response.success(emptyList<String>(), Headers.headersOf("X-Recommendation-Status", "empty"))
        }
        assertTrue(result.body()!!.isEmpty())
    }
    @Test fun unauthorizedDoesNotRetry() = runBlocking {
        val result = RecommendationRecovery.load(pause = { fail("Unexpected retry") }) {
            Response.error<String>(401, "".toResponseBody())
        }
        assertEquals(401, result.code())
    }
    @Test fun persistentServiceFailureStopsAfterFiveAttempts() = runBlocking {
        var calls = 0
        try {
            RecommendationRecovery.load(pause = {}) {
                calls++; Response.error<String>(503, "".toResponseBody())
            }
            fail("Must report temporary failure")
        } catch (_: IOException) { assertEquals(5, calls) }
    }
    @Test fun connectionFailureCanRecover() = runBlocking {
        var calls = 0
        val result = RecommendationRecovery.load(pause = {}) {
            if (++calls == 1) throw IOException("timeout")
            Response.success("song")
        }
        assertEquals("song",result.body())
    }
    @Test fun cancellationNeverRetries() = runBlocking {
        try {
            RecommendationRecovery.load<String>(pause = { fail("Unexpected retry") }) {
                throw CancellationException("Track changed")
            }
            fail("Cancellation must propagate")
        } catch (_: CancellationException) { }
    }
}
