package com.mformusic.frontend.data

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import com.mformusic.frontend.model.SongResponse
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.nio.file.Files

class RecommendationStoreTest {
    private fun song(id: String) = SongResponse(null,id,"Title $id","Artist",120,null,null,"https://audio.test/$id",0,false)

    @Test fun lastSuccessfulFeedSurvivesRestartAndEmptyRefresh() = runBlocking {
        val directory = Files.createTempDirectory("recommendations").toFile()
        val file = directory.resolve("feed.preferences_pb")
        var scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        try {
            var data = PreferenceDataStoreFactory.create(scope = scope) { file }
            RecommendationStore(data,"release").save(1,listOf(song("a"),song("b")))
            scope.coroutineContext[Job]!!.cancelAndJoin()
            scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
            data = PreferenceDataStoreFactory.create(scope = scope) { file }
            val store = RecommendationStore(data,"release")
            store.save(1,emptyList())
            assertEquals(listOf(song("a"),song("b")),store.read(1))
            store.save(1,listOf(song("new")))
            assertEquals(listOf(song("new")),store.read(1))
        } finally { scope.coroutineContext[Job]!!.cancelAndJoin(); directory.deleteRecursively() }
    }

    @Test fun isolatesAccountsAndEnvironmentsAndHandlesCorruption() = runBlocking {
        val directory = Files.createTempDirectory("recommendations").toFile()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        try {
            val data = PreferenceDataStoreFactory.create(scope = scope) { directory.resolve("feed.preferences_pb") }
            val release = RecommendationStore(data,"release")
            release.save(1,listOf(song("a"),song("a")))
            release.save(2,listOf(song("private")))
            assertEquals(listOf(song("a")),release.read(1))
            assertEquals(listOf(song("private")),release.read(2))
            assertTrue(release.read(3).isEmpty())
            assertTrue(RecommendationStore(data,"debug").read(1).isEmpty())
            data.edit { it[stringPreferencesKey("for_you_v1_release_1")] = "broken json" }
            assertTrue(release.read(1).isEmpty())
            release.save(1,listOf(song("recovered")))
            assertEquals(listOf(song("recovered")),release.read(1))
        } finally { scope.coroutineContext[Job]!!.cancelAndJoin(); directory.deleteRecursively() }
    }
}
