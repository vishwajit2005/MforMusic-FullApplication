package com.mformusic.backend.service;

import com.mformusic.backend.model.Song;
import com.mformusic.backend.repository.SongRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;
import java.lang.reflect.Proxy;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.RejectedExecutionException;
import static org.junit.jupiter.api.Assertions.*;

class SongUploadTimingTest {
    private SongService service;
    private Song cached;
    private int uploads;
    private boolean reject;
    private boolean failSave;
    private TestTransactionManager manager;
    private TransactionTemplate transaction;

    @BeforeEach void setup() {
        manager = new TestTransactionManager();
        transaction = new TransactionTemplate(manager);
        service = new SongService();
        var repository = (SongRepository) Proxy.newProxyInstance(
                SongRepository.class.getClassLoader(), new Class<?>[]{SongRepository.class}, (proxy, method, args) -> {
                    return switch (method.getName()) {
                        case "findByExternalTrackId" -> Optional.ofNullable(cached);
                        case "save" -> {
                            if (failSave) throw new IllegalStateException("DB save failed");
                            Song song = (Song) args[0]; song.setId(37L); yield song;
                        }
                        default -> throw new AssertionError(method.getName());
                    };
                });
        ReflectionTestUtils.setField(service, "songRepository", repository);
        ReflectionTestUtils.setField(service, "externalMusicService", new ExternalMusicService() {
            @Override public java.util.List<Map<String, Object>> getSongsByIds(java.util.List<String> ids) {
                assertEquals(java.util.List.of("external-id"), ids);
                return java.util.List.of(searchSongOnSaavn("unused"));
            }
            @Override public Map<String, Object> searchSongOnSaavn(String query) {
                return Map.of("id", "external-id", "title", "Song", "artistName", "Artist",
                        "duration", 120, "thumbnailUrl", "https://example.test/art",
                        "audioUrl", "https://example.test/audio");
            }
        });
        ReflectionTestUtils.setField(service, "asyncUploadService", new AsyncUploadService() {
            @Override public void uploadToSupabaseAsync(Long id, String url) {
                assertTrue(manager.committed, "Separate worker must only be submitted after DB commit");
                assertEquals(37L, id); assertEquals("https://example.test/audio", url);
                uploads++;
                if (reject) throw new RejectedExecutionException("executor full");
            }
        });
    }

    @Test void cacheMissDispatchesOnlyAfterCommit() {
        transaction.executeWithoutResult(status -> {
            assertNotNull(service.playOrCacheSong("Song", null));
            assertEquals(0, uploads);
        });
        assertEquals(1, uploads);
    }

    @Test void exactIdPlaybackAlsoWaitsForCommit() {
        transaction.executeWithoutResult(status -> {
            assertEquals("external-id", service.playByExternalId("external-id", null).getExternalTrackId());
            assertEquals(0, uploads);
        });
        assertEquals(1, uploads);
    }

    @Test void rollbackNeverDispatchesUpload() {
        transaction.executeWithoutResult(status -> {
            service.playOrCacheSong("Song", null);
            status.setRollbackOnly();
        });
        assertFalse(manager.committed); assertEquals(0, uploads);
    }

    @Test void exceptionAfterSaveNeverDispatchesUpload() {
        assertThrows(IllegalStateException.class, () -> transaction.executeWithoutResult(status -> {
            service.playOrCacheSong("Song", null);
            throw new IllegalStateException("history failed");
        }));
        assertEquals(0, uploads);
    }

    @Test void failedSaveNeverDispatchesUpload() {
        failSave = true;
        assertThrows(IllegalStateException.class,
                () -> transaction.executeWithoutResult(status -> service.playOrCacheSong("Song", null)));
        assertEquals(0, uploads);
    }

    @Test void previouslyFailedUploadIsRecoveredOnNextPlay() {
        cached = song(false);
        transaction.executeWithoutResult(status -> {
            service.playOrCacheSong("Song", null);
            assertEquals(0, uploads);
        });
        assertEquals(1, uploads); assertEquals(2, cached.getPlayCount());
    }

    @Test void uploadedCacheHitDoesNotDispatchAgain() {
        cached = song(true);
        transaction.executeWithoutResult(status -> service.playOrCacheSong("Song", null));
        assertEquals(0, uploads); assertEquals(2, cached.getPlayCount());
    }

    @Test void executorRejectionDoesNotFailCommittedPlay() {
        reject = true;
        assertDoesNotThrow(() -> transaction.executeWithoutResult(status -> service.playOrCacheSong("Song", null)));
        assertTrue(manager.committed); assertEquals(1, uploads);
    }

    private Song song(boolean uploaded) {
        Song song = new Song(); song.setId(37L); song.setExternalTrackId("external-id");
        song.setTitle("Song"); song.setStoredInS3(uploaded); song.setPlayCount(1); return song;
    }

    private static class TestTransactionManager extends AbstractPlatformTransactionManager {
        boolean committed;
        @Override protected Object doGetTransaction() { return new Object(); }
        @Override protected void doBegin(Object transaction, TransactionDefinition definition) {}
        @Override protected void doCommit(DefaultTransactionStatus status) { committed = true; }
        @Override protected void doRollback(DefaultTransactionStatus status) {}
    }
}
