package com.mformusic.backend.service;

import com.mformusic.backend.dto.TelemetryEventDto;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;
import org.springframework.test.web.client.MockRestServiceServer;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;

class TelemetryForwardingTest {
    @Test void saturatedExecutorDoesNotThrowOrSendOnCaller() {
        var service=new TelemetryService(null,new RestTemplate(),null,null);
        ReflectionTestUtils.setField(service,"fastApiEnabled",true);
        ReflectionTestUtils.setField(service,"fastApiBaseUrl","http://mlops.invalid");
        ReflectionTestUtils.setField(service,"taskExecutor",(Executor) task -> {
            throw new RejectedExecutionException("full");
        });
        assertDoesNotThrow(() -> service.forwardToFastApi(new TelemetryEventDto()));
    }
    @Test void failedForwardIsAttemptedOnceAndDoesNotThrow() {
        var client=new RestTemplate();
        var server=MockRestServiceServer.bindTo(client).build();
        server.expect(requestTo("http://mlops.invalid/api/v1/interactions/ingest")).andRespond(withServerError());
        var service=new TelemetryService(null,client,null,null);
        ReflectionTestUtils.setField(service,"fastApiEnabled",true);
        ReflectionTestUtils.setField(service,"fastApiBaseUrl","http://mlops.invalid");
        ReflectionTestUtils.setField(service,"taskExecutor",(Executor) Runnable::run);
        assertDoesNotThrow(() -> service.forwardToFastApi(new TelemetryEventDto()));
        server.verify();
    }
    @Test void disabledOrMissingUrlDoesNotSubmit() {
        var service=new TelemetryService(null,new RestTemplate(),null,null);
        ReflectionTestUtils.setField(service,"taskExecutor",(Executor) task -> fail("Must not submit"));
        service.forwardToFastApi(new TelemetryEventDto());
        ReflectionTestUtils.setField(service,"fastApiEnabled",true);
        ReflectionTestUtils.setField(service,"fastApiBaseUrl"," ");
        service.forwardToFastApi(new TelemetryEventDto());
    }
}
