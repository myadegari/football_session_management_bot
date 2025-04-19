from functools import wraps, partial
from inspect import signature, Parameter
from typing import Any, Callable, Dict, Optional, TypeVar, Union
import warnings

T = TypeVar('T')

class Dependency:
    """Wrapper for dependency functions with configuration."""
    def __init__(
        self,
        dependency: Callable[..., T],
        *,
        use_cache: bool = True,
        override: Optional[Dict[str, Any]] = None
    ):
        self.dependency = dependency
        self.use_cache = use_cache
        self.override = override or {}
    
    def __call__(self, **kwargs: Any) -> T:
        # Apply overrides
        call_kwargs = {**kwargs, **self.override}
        return self.dependency(**call_kwargs)

def Depends(
    dependency: Callable[..., T],
    *,
    use_cache: bool = True,
    **override: Any
) -> T:
    """Declare a dependency, similar to FastAPI's Depends."""
    return Dependency(dependency, use_cache=use_cache, override=override)

class DependencyInjector:
    """Core dependency injection system with caching."""
    def __init__(self):
        self._cache: Dict[str, Any] = {}
    
    def inject(self,func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to enable dependency injection for a function."""
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Get the function signature
            sig = signature(func)
            bound_args = sig.bind_partial(*args, **kwargs)
            
            # Process each parameter
            for name, param in sig.parameters.items():
                if name not in bound_args.arguments:
                    if isinstance(param.default, Dependency):
                        # Resolve the dependency
                        dep = param.default
                        cache_key = f"{dep.dependency.__name__}:{id(dep.dependency)}"
                        
                        if dep.use_cache and cache_key in self._cache:
                            # Use cached value
                            bound_args.arguments[name] = self._cache[cache_key]
                        else:
                            # Resolve the dependency
                            dependency_args = {}
                            
                            # Check if the dependency has its own dependencies
                            if hasattr(dep.dependency, '_injected'):
                                dependency_args = self.inject(dep.dependency)(**dep.override)
                            
                            result = dep(**dependency_args)
                            
                            # Handle generator-based dependencies (like get_db)
                            if hasattr(result, '__iter__') and hasattr(result, '__next__'):
                                try:
                                    result = next(result)
                                except StopIteration:
                                    raise ValueError(f"Generator dependency {dep.dependency.__name__} exhausted")
                            
                            bound_args.arguments[name] = result
                            
                            if dep.use_cache:
                                self._cache[cache_key] = result
            
            return func(*bound_args.args, **bound_args.kwargs)
        
        # Mark the function as injected
        wrapper._injected = True
        return wrapper
    
    def clear_cache(self):
        """Clear all cached dependencies."""
        self._cache.clear()

# Global injector instance
injector = DependencyInjector()

# Shortcut decorator
inject = injector.inject