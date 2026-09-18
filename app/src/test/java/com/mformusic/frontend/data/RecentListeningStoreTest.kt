package com.mformusic.frontend.data

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test
import java.nio.file.Files

class RecentListeningStoreTest {
    @Test fun restoresAcrossStoreRecreationAndKeepsFourPriorSongs() = runBlocking {
        val directory = Files.createTempDirectory("listening-test").toFile()
        val file = directory.resolve("history.preferences_pb")
        var scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        try {
            var store = RecentListeningStore(PreferenceDataStoreFactory.create(scope = scope) { file })
            for (id in listOf("a", "b", "c", "d", "current")) store.record(1, id)
            assertEquals(listOf("d", "c", "b", "a"), RecentListeningStore.context(store.read(1), "current"))
            scope.coroutineContext[Job]!!.cancelAndJoin()
            scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
            store = RecentListeningStore(PreferenceDataStoreFactory.create(scope = scope) { file })
            assertEquals(listOf("current", "d", "c", "b", "a"), store.read(1))
            store.record(1, "next")
            assertEquals(listOf("current", "d", "c", "b"), RecentListeningStore.context(store.read(1), "next"))
        } finally { scope.coroutineContext[Job]!!.cancelAndJoin(); directory.deleteRecursively() }
    }

    @Test fun historiesAreAccountScopedAndRepeatedTracksMoveToFront() = runBlocking {
        withStore { store ->
            store.record(1, "a"); store.record(1, "b"); store.record(2, "private"); store.record(1, "a")
            assertEquals(listOf("a", "b"), store.read(1))
            assertEquals(listOf("private"), store.read(2))
            assertEquals(emptyList<String>(), store.read(3))
            assertEquals(listOf("b"), RecentListeningStore.context(store.read(1), "a"))
        }
    }

    @Test fun rapidConcurrentWritesDoNotLoseEntries() = runBlocking {
        withStore { store ->
            coroutineScope { listOf("a", "b", "c", "d").map { id -> async { store.record(1, id) } }.awaitAll() }
            assertEquals(setOf("a", "b", "c", "d"), store.read(1).toSet())
        }
    }

    @Test fun jsonPreservesIdsWithSeparatorsAndCapsHistory() = runBlocking {
        withStore { store ->
            for (id in listOf("old", "a", "b", "c", "id,comma", "id\"quote")) store.record(1, id)
            assertEquals(listOf("id\"quote", "id,comma", "c", "b", "a"), store.read(1))
        }
    }

    @Test fun corruptHistoryRecoversOnNextPlay() = runBlocking {
        val directory = Files.createTempDirectory("listening-test").toFile()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        try {
            val data = PreferenceDataStoreFactory.create(scope = scope) { directory.resolve("history.preferences_pb") }
            data.edit { it[stringPreferencesKey("recent_played_ids_1")] = "invalid json" }
            val store = RecentListeningStore(data)
            assertTrue(store.read(1).isEmpty())
            store.record(1, "new")
            assertEquals(listOf("new"), store.read(1))
        } finally { scope.coroutineContext[Job]!!.cancelAndJoin(); directory.deleteRecursively() }
    }

    private suspend fun withStore(block: suspend (RecentListeningStore) -> Unit) {
        val directory = Files.createTempDirectory("listening-test").toFile()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        try {
            block(RecentListeningStore(PreferenceDataStoreFactory.create(scope = scope) { directory.resolve("history.preferences_pb") }))
        } finally { scope.coroutineContext[Job]!!.cancelAndJoin(); directory.deleteRecursively() }
    }
}
