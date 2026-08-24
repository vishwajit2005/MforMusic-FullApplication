package com.mformusic.frontend.network

import com.mformusic.frontend.BuildConfig
import com.mformusic.frontend.data.TokenDataStore
import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Singleton Retrofit client with JWT auth interceptor.
 * Must call init() before first use (done in MainActivity.onCreate).
 */
object RetrofitClient {

    private var tokenDataStore: TokenDataStore? = null

    fun init(tokenDataStore: TokenDataStore) {
        this.tokenDataStore = tokenDataStore
    }

    // Auth interceptor: reads token from DataStore and adds Bearer header
    private val authInterceptor = Interceptor { chain ->
        val token = runBlocking { tokenDataStore?.getToken() }
        val request = if (!token.isNullOrBlank()) {
            chain.request().newBuilder()
                .addHeader("Authorization", "Bearer $token")
                .build()
        } else {
            chain.request()
        }
        chain.proceed(request)
    }

    private val okHttpClient = OkHttpClient.Builder()
        .addInterceptor(authInterceptor)
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val retrofit: Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.BASE_URL)
        .client(okHttpClient)
        .addConverterFactory(GsonConverterFactory.create())
        .build()

    val musicApiService: MusicApiService = retrofit.create(MusicApiService::class.java)

    val telemetryApiService: TelemetryApiService by lazy {
    retrofit.create(TelemetryApiService::class.java)
}
}
