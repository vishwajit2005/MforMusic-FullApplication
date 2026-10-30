package com.mformusic.frontend.network

import com.mformusic.frontend.model.SongResponse
import retrofit2.Response

/**
 * Play exactly the song the user tapped (by its JioSaavn ID).
 * Searching by title can return a different version (e.g. a remix or a
 * compilation copy), which also sends the wrong song ID to the recommender.
 * Falls back to the old title search only if the ID lookup fails.
 */
suspend fun MusicApiService.playExact(song: SongResponse): Response<SongResponse> {
    if (song.externalTrackId.isNotBlank()) {
        val byId = playSongById(song.externalTrackId)
        if (byId.isSuccessful && byId.body() != null) return byId
    }
    return playOrCacheSong(song.title)
}
