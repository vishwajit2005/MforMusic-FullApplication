package com.mformusic.frontend.network

import com.mformusic.frontend.telemetry.TelemetryEvent
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.POST

interface TelemetryApiService {
    @POST("api/v1/telemetry/interactions")
    suspend fun postInteraction(@Body event: TelemetryEvent): Response<Map<String, Any>>
}