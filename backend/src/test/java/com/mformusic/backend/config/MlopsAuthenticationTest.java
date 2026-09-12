package com.mformusic.backend.config;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.client.MockRestServiceServer;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class MlopsAuthenticationTest {
    @Test
    void sendsKeyOnlyToConfiguredMlopsOriginAndPath() {
        var client = new AppConfig().restTemplate("https://mlops.example/internal", "test-service-key");
        var server = MockRestServiceServer.bindTo(client).build();
        server.expect(requestTo("https://mlops.example/internal/health"))
                .andExpect(header("X-MforMusic-Key", "test-service-key")).andRespond(withSuccess());
        server.expect(requestTo("https://wrapper.example/songs"))
                .andExpect(headerDoesNotExist("X-MforMusic-Key")).andRespond(withSuccess());
        server.expect(requestTo("https://mlops.example/internal-other/health"))
                .andExpect(headerDoesNotExist("X-MforMusic-Key")).andRespond(withSuccess());
        server.expect(requestTo("http://mlops.example/internal/health"))
                .andExpect(headerDoesNotExist("X-MforMusic-Key")).andRespond(withSuccess());
        for (String url : new String[]{"https://mlops.example/internal/health", "https://wrapper.example/songs",
                "https://mlops.example/internal-other/health", "http://mlops.example/internal/health"}) {
            client.getForObject(url, String.class);
        }
        server.verify();
    }

    @Test
    void localDefaultsSendNoKey() {
        var client = new AppConfig().restTemplate("http://localhost:8000", "");
        var server = MockRestServiceServer.bindTo(client).build();
        server.expect(requestTo("http://localhost:8000/health"))
                .andExpect(headerDoesNotExist("X-MforMusic-Key")).andRespond(withSuccess());
        client.getForObject("http://localhost:8000/health", String.class);
        server.verify();
    }
}
