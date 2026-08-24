package com.mformusic.frontend.worker

import android.content.Context
import android.util.Log
import androidx.work.*
import com.mformusic.frontend.data.local.AppDatabase
import com.mformusic.frontend.data.repository.DownloadRepository
import com.mformusic.frontend.network.RetrofitClient
import java.io.File

/**
 * PredictiveCacheWorker — Phase 5 Smart Local Caching
 *
 * Runs in the background (WiFi-only, battery-not-low) to pre-download
 * the top [SONGS_TO_PREFETCH] songs from the personalised recommendation
 * feed so they are available offline before the user explicitly taps them.
 *
 * Triggered by [ForYouViewModel] after recommendations successfully load.
 *
 * Design decisions:
 *  - WiFi-only constraint prevents unwanted mobile data usage.
 *  - Skips songs that are already present in the Room DB (localFilePath check).
 *  - Runs as a one-time [CoroutineWorker] re-scheduled on every For You
 *    refresh so the cache tracks evolving recommendations.
 */
class PredictiveCacheWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "PredictiveCacheWorker"
        private const val SONGS_TO_PREFETCH = 5
        const val WORK_NAME = "mformusic_predictive_cache"

        fun enqueue(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.UNMETERED) // WiFi only
                .setRequiresBatteryNotLow(true)
                .build()

            val request = OneTimeWorkRequestBuilder<PredictiveCacheWorker>()
                .setConstraints(constraints)
                .addTag(WORK_NAME)
                .build()

            WorkManager.getInstance(context).enqueueUniqueWork(
                WORK_NAME,
                ExistingWorkPolicy.REPLACE,
                request
            )
            Log.d(TAG, "Predictive cache work enqueued.")
        }
    }

    override suspend fun doWork(): Result {
        Log.i(TAG, "Predictive cache worker started.")
        val ctx = applicationContext
        return try {
            val api = RetrofitClient.musicApiService
            val dao = AppDatabase.getDatabase(ctx).downloadedSongDao()

            // Fetch fresh top-N recommendations
            val response = api.getRecommendations(n = SONGS_TO_PREFETCH)
            if (!response.isSuccessful || response.body() == null) {
                Log.w(TAG, "Could not fetch recs (${response.code()}) — retrying later.")
                return Result.retry()
            }

            var cached = 0
            for (song in response.body()!!.take(SONGS_TO_PREFETCH)) {
                // Skip if already in Room DB and local file still exists
                val existing = dao.getDownloadedSong(song.externalTrackId)
                if (existing != null && File(existing.localFilePath).exists()) {
                    Log.d(TAG, "Already cached: ${song.title}")
                    continue
                }

                // Skip songs with no playable URL
                if (song.s3Url.isNullOrBlank() && song.saavnUrl.isBlank()) {
                    Log.d(TAG, "No audio URL for ${song.title} — skipping.")
                    continue
                }

                Log.i(TAG, "Pre-caching: ${song.title}")
                val success = DownloadRepository.downloadSong(ctx, song)
                if (success) cached++
            }

            Log.i(TAG, "Predictive cache complete: $cached new songs pre-fetched.")
            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "Predictive cache failed: ${e.message}", e)
            Result.retry()
        }
    }
}
