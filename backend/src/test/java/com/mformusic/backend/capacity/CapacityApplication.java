package com.mformusic.backend.capacity;

import com.mformusic.backend.BackendApplication;
import com.zaxxer.hikari.HikariDataSource;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import java.lang.management.*;
import javax.management.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

/** Run with the test classpath, never shipped in the production artifact. */
public class CapacityApplication {
    public static void main(String[] args) throws Exception {
        SpringApplication app=new SpringApplication(BackendApplication.class, CapacityTestConfig.class);
        app.setAdditionalProfiles("capacity");
        ConfigurableApplicationContext context=app.run(args);
        HikariDataSource pool=context.getBean(HikariDataSource.class);
        ThreadPoolTaskExecutor executor=context.getBean("taskExecutor", ThreadPoolTaskExecutor.class);
        MeterRegistry meters=context.getBean(MeterRegistry.class);
        var stub=context.getBean(CapacityTestConfig.BoundaryStub.class);
        Path output=Path.of(System.getProperty("capacity.metrics", "metrics.jsonl"));
        var writer=Files.newBufferedWriter(output);
        var scheduler=Executors.newSingleThreadScheduledExecutor();
        scheduler.scheduleAtFixedRate(() -> {
            try {
                var mx=pool.getHikariPoolMXBean();
                MBeanServer server=ManagementFactory.getPlatformMBeanServer();
                long busy=-1, threads=-1, max=-1, connections=-1;
                for(ObjectName name:server.queryNames(new ObjectName("*:type=ThreadPool,*"),null)) {
                    busy=((Number)server.getAttribute(name,"currentThreadsBusy")).longValue();
                    threads=((Number)server.getAttribute(name,"currentThreadCount")).longValue();
                    max=((Number)server.getAttribute(name,"maxThreads")).longValue();
                    connections=((Number)server.getAttribute(name,"connectionCount")).longValue();
                }
                var os=(com.sun.management.OperatingSystemMXBean)ManagementFactory.getOperatingSystemMXBean();
                var timeouts=meters.find("hikaricp.connections.timeout").counter();
                String row=String.format(Locale.ROOT,
                    "{\"time\":%d,\"db_active\":%d,\"db_idle\":%d,\"db_pending\":%d,\"db_timeouts\":%.0f,\"tomcat_busy\":%d,\"tomcat_threads\":%d,\"tomcat_max\":%d,\"connections\":%d,\"async_active\":%d,\"async_queue\":%d,\"async_completed\":%d,\"saavn_calls\":%d,\"fastapi_calls\":%d,\"blocked_egress\":%d,\"uploads\":%d,\"process_cpu\":%.4f,\"system_cpu\":%.4f,\"heap_bytes\":%d}%n",
                    System.currentTimeMillis(),mx.getActiveConnections(),mx.getIdleConnections(),mx.getThreadsAwaitingConnection(),
                    timeouts==null?0:timeouts.count(),busy,threads,max,connections,executor.getActiveCount(),
                    executor.getThreadPoolExecutor().getQueue().size(),executor.getThreadPoolExecutor().getCompletedTaskCount(),
                    stub.saavn.get(),stub.fastapi.get(),stub.blocked.get(),stub.uploads.get(),os.getProcessCpuLoad(),os.getCpuLoad(),
                    ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed());
                writer.write(row); writer.flush();
                if(mx.getThreadsAwaitingConnection()>0 && System.currentTimeMillis()/1000%15==0) {
                    StringBuilder dump=new StringBuilder();
                    for(var info:ManagementFactory.getThreadMXBean().dumpAllThreads(false,false)) {
                        if(info.getThreadName().startsWith("http-nio") || info.getThreadName().startsWith("bg-upload")) {
                            dump.append(info.getThreadName()).append(" ").append(info.getThreadState()).append('\n');
                            for(var frame:info.getStackTrace()) dump.append("  ").append(frame).append('\n');
                        }
                    }
                    Files.writeString(output.resolveSibling("threads-"+System.currentTimeMillis()+".txt"),dump.toString());
                }
            } catch(Exception e) { e.printStackTrace(); }
        },0,1,TimeUnit.SECONDS);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            scheduler.shutdownNow();
            try { writer.close(); } catch(Exception ignored) { }
        }));
        System.out.println("CAPACITY_METRICS_READY " + output);
    }
}
