package ai.lightyear.carddemo;

import java.sql.SQLException;
import java.util.Map;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
public final class InteractionController {
    private final InteractionEngine engine;
    public InteractionController(InteractionEngine engine){this.engine=engine;}
    @PostMapping(path="/api/interaction",consumes=MediaType.APPLICATION_JSON_VALUE,produces=MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<InteractionEngine.Response> interaction(@RequestBody InteractionEngine.Request request)throws SQLException {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(engine.interact(request));
    }
    @GetMapping("/not-in-this-slice")
    public ResponseEntity<Map<String,String>> outside(){return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(Map.of("message","This option is not in slice 1."));}
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String,String>> invalid(IllegalArgumentException error){
        return ResponseEntity.badRequest().cacheControl(CacheControl.noStore()).body(Map.of("error","Interaction or session rejected."));
    }
    @ExceptionHandler({SQLException.class,IllegalStateException.class,UnsupportedOperationException.class})
    public ResponseEntity<Map<String,String>> unavailable(Exception error){
        // SQL diagnostics may contain account data; never serialize exception text or statement parameters.
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).cacheControl(CacheControl.noStore()).body(Map.of("error","This interaction could not be completed. No changes were committed."));
    }
}
