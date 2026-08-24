package com.mformusic.frontend.network

import com.mformusic.frontend.model.AuthResponse
import com.mformusic.frontend.model.LoginRequest
import com.mformusic.frontend.model.RegisterRequest
import com.mformusic.frontend.model.SongResponse
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query
import retrofit2.http.Path

interface MusicApiService {

    // ── Auth ──────────────────────────────────────────────────────────────────

    @POST("api/v1/auth/register")
    suspend fun register(@Body request: RegisterRequest): Response<AuthResponse>

    @POST("api/v1/auth/login")
    suspend fun login(@Body request: LoginRequest): Response<AuthResponse>

    // ── Songs (JWT required — handled by RetrofitClient interceptor) ──────────

    @POST("api/v1/songs/play")
    suspend fun playOrCacheSong(@Query("songName") songName: String): Response<SongResponse>

    @GET("api/v1/songs/suggestions")
    suspend fun getSearchSuggestions(@Query("query") query: String): Response<List<SongResponse>>

    @GET("api/v1/songs/recent")
    suspend fun getRecentSongs(): Response<List<SongResponse>>

    @POST("api/v1/songs/{songId}/like")
    suspend fun likeSong(@Path("songId") songId: Long): Response<SongResponse>

    @POST("api/v1/songs/{songId}/unlike")
    suspend fun unlikeSong(@Path("songId") songId: Long): Response<SongResponse>

    @GET("api/v1/songs/liked")
    suspend fun getLikedSongs(): Response<List<SongResponse>>

    // ── Recommendations (JWT required — personalised "For You" feed) ──────────

    @GET("api/v1/recommendations")
    suspend fun getRecommendations(
        @Query("n") n: Int = 20
    ): Response<List<SongResponse>>
}