package com.mformusic.backend.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.net.URLConnection;

@Service
public class CloudStorageService {

    private static final Logger log = LoggerFactory.getLogger(CloudStorageService.class);

    @Value("${supabase.url}")
    private String supabaseUrl;

    @Value("${supabase.anonKey}")
    private String anonKey;

    @Value("${supabase.bucketName}")
    private String bucketName;

    private final RestTemplate restTemplate = new RestTemplate();

    /**
     * Streams audio from JioSaavn URL directly to Supabase — avoids loading the entire
     * MP3 file into memory (prevents OOM on large files or concurrent uploads).
     */
    public String uploadTrackFromUrl(String audioUrl, String trackId) {
        String fileName = trackId + ".mp3";
        String uploadUrl = supabaseUrl + "/storage/v1/object/" + bucketName + "/" + fileName;

        try {
            log.info("Starting streaming upload to Supabase: {}", fileName);

            URL sourceUrl = new URL(audioUrl);
            URLConnection connection = sourceUrl.openConnection();
            connection.setConnectTimeout(15_000);
            connection.setReadTimeout(120_000);
            connection.connect();

            final long contentLength = connection.getContentLengthLong();

            HttpHeaders headers = new HttpHeaders();
            headers.set("Authorization", "Bearer " + anonKey);
            headers.set("apikey", anonKey);
            headers.setContentType(MediaType.valueOf("audio/mpeg"));
            if (contentLength > 0) {
                headers.setContentLength(contentLength);
            }

            // Stream via RequestCallback: read from JioSaavn, write to Supabase in 8KB chunks
            String publicUrl = restTemplate.execute(
                    uploadUrl,
                    HttpMethod.POST,
                    request -> {
                        request.getHeaders().addAll(headers);
                        try (InputStream in = connection.getInputStream();
                             OutputStream out = request.getBody()) {
                            byte[] buffer = new byte[8192];
                            int read;
                            while ((read = in.read(buffer)) != -1) {
                                out.write(buffer, 0, read);
                            }
                        }
                    },
                    response -> {
                        if (response.getStatusCode().is2xxSuccessful()) {
                            return supabaseUrl + "/storage/v1/object/public/" + bucketName + "/" + fileName;
                        }
                        log.warn("Supabase upload returned non-2xx: {}", response.getStatusCode());
                        return null;
                    }
            );

            if (publicUrl != null) {
                log.info("Supabase upload successful: {}", publicUrl);
            }
            return publicUrl;

        } catch (Exception e) {
            log.error("Supabase upload error for track {}: {}", trackId, e.getMessage());
            return null;
        }
    }

    /**
     * Deletes a track from Supabase storage (called during LRU eviction).
     */
    public void deleteTrackFromS3(String trackId) {
        String fileName = trackId + ".mp3";
        String deleteUrl = supabaseUrl + "/storage/v1/object/" + bucketName + "/" + fileName;

        try {
            log.info("Deleting from Supabase: {}", fileName);
            HttpHeaders headers = new HttpHeaders();
            headers.set("Authorization", "Bearer " + anonKey);
            headers.set("apikey", anonKey);

            HttpEntity<Void> requestEntity = new HttpEntity<>(headers);
            restTemplate.exchange(deleteUrl, HttpMethod.DELETE, requestEntity, String.class);
            log.info("Supabase delete successful: {}", fileName);
        } catch (Exception e) {
            log.error("Supabase delete error for track {}: {}", trackId, e.getMessage());
            throw new RuntimeException("Failed to delete track from Supabase: " + e.getMessage());
        }
    }
}