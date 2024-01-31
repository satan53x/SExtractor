# encoding: utf-8
# to_json.rb
# author: dice2000
# original author: aoitaku
# https://gist.github.com/aoitaku/7822424
# 
# to_yaml.rbをjsonに対応させたもの
# デバッグ途中
#
# Area.rvdata, Scripts.rvdata未対応
require 'jsonable'
require 'zlib'
require_relative 'rgss2'

def getName(file)
	File.basename(file).split('.')[0]
end

Ignore_filename_list = ['Areas', 'Scripts']
def to_json(datadir, jsondir)
	if !File.directory?(datadir)
		Dir.mkdir(datadir)
	end
	if !File.directory?(jsondir)
		Dir.mkdir(jsondir)
	end
	#p datadir
	files = Dir.entries(datadir).select { |filename|
		ret = File.file?(File.join(datadir, filename))
		if ret
			name = getName(filename)
			ret = ! Ignore_filename_list.include?(name)
		end
		ret
	}
	files.each { |filename|
		data = ''
		p filename
		File.open(File.join(datadir, filename), 'rb') { |file|
			data = Marshal.load(file.read)
			if data.is_a?(Array)
				data.each{ |d|
					d.unpack_names if d != nil
				}
			elsif data.is_a?(Hash)
				if data.size != 0
					data.each_value{|v|
						v.unpack_names
					}
				end
			else
				data.unpack_names
			end
		}
		jsonpath = File.join(jsondir, filename+'.json')
		File.open(jsonpath, 'w:utf-8') do |file|
			file.write(data.to_json)
		end
	}
end

args = ARGV
datadir = args.length<=0 ? 'Data' : args[0]
jsondir = args.length<=1 ? 'Json' : args[1]
to_json(datadir, jsondir)