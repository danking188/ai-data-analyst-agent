#!/usr/bin/env ruby

require "yaml"

path = ARGV.fetch(0, "docs/api/openapi.yaml")
document = YAML.load_file(path)
errors = []

errors << "openapi must be 3.1.x" unless document["openapi"].to_s.start_with?("3.1.")
errors << "info.version is required" if document.dig("info", "version").to_s.empty?
errors << "paths is required" unless document["paths"].is_a?(Hash)

http_methods = %w[get post put patch delete]
operation_ids = []
references = []

walk = lambda do |node|
  case node
  when Hash
    node.each do |key, value|
      references << value if key == "$ref" && value.is_a?(String)
      walk.call(value)
    end
  when Array
    node.each { |value| walk.call(value) }
  end
end
walk.call(document)

references.uniq.each do |reference|
  next unless reference.start_with?("#/")

  current = document
  reference[2..].split("/").each do |raw_part|
    part = raw_part.gsub("~1", "/").gsub("~0", "~")
    unless current.is_a?(Hash) && current.key?(part)
      errors << "missing reference: #{reference}"
      break
    end
    current = current[part]
  end
end

resolve_local = lambda do |node|
  next node unless node.is_a?(Hash) && node["$ref"].is_a?(String) && node["$ref"].start_with?("#/")

  current = document
  node["$ref"][2..].split("/").each do |raw_part|
    part = raw_part.gsub("~1", "/").gsub("~0", "~")
    current = current[part]
  end
  current
end

document.fetch("paths", {}).each do |route, path_item|
  placeholders = route.scan(/\{([^}]+)\}/).flatten
  path_parameters = Array(path_item["parameters"])

  http_methods.each do |method|
    operation = path_item[method]
    next unless operation

    operation_id = operation["operationId"]
    if operation_id.to_s.empty?
      errors << "#{method.upcase} #{route}: operationId is required"
    else
      operation_ids << operation_id
    end

    responses = operation["responses"]
    errors << "#{method.upcase} #{route}: responses are required" unless responses.is_a?(Hash) && !responses.empty?

    declared = (path_parameters + Array(operation["parameters"])).each_with_object([]) do |raw_parameter, names|
      parameter = resolve_local.call(raw_parameter)
      names << parameter["name"] if parameter.is_a?(Hash) && parameter["in"] == "path"
    end
    missing_parameters = placeholders - declared
    unless missing_parameters.empty?
      errors << "#{method.upcase} #{route}: missing path parameters #{missing_parameters.join(', ')}"
    end
  end
end

duplicates = operation_ids.group_by(&:itself).select { |_key, values| values.length > 1 }.keys
errors << "duplicate operationId: #{duplicates.join(', ')}" unless duplicates.empty?

if errors.empty?
  puts "OpenAPI validation passed: #{document['paths'].length} paths, #{operation_ids.length} operations, #{references.length} references"
  exit 0
end

warn "OpenAPI validation failed:"
errors.each { |error| warn "- #{error}" }
exit 1
